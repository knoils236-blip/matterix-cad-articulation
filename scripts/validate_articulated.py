"""Acceptance run: load an articulated asset through Matterix (2 envs) and drive every joint.

    MATTERIX_PATH=<matterix checkout> python validate_articulated.py --cfg <cfg.py>:<CLASS> --out <result.json>
        [--fractions 0.25 0.75] [--tol 1e-3] [--seconds 4] [--no-link-collisions]

Per env i every joint is commanded to lower + fractions[i] * (upper - lower) and held. A dropped
500 mL beaker (existing Matterix asset) must stay on top of the asset. Pass = all joint errors < tol,
zero root drift, beaker resting above the asset's top minus 5 cm. Revolute joints are in radians, so
for them the error and --tol are radians (the JSON keys keep the M suffix).
--no-link-collisions runs a temporary copy with every link collider disabled: the control
experiment that separates kinematics/drive problems from internal contacts.
Do not run two Matterix processes at once (shared datasets/dataset.hdf5 lock).
"""
import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--cfg", required=True, help="path/to/cfg.py:CLASS (a MatterixArticulationCfg subclass)")
parser.add_argument("--out", required=True)
parser.add_argument("--fractions", type=float, nargs=2, default=[0.25, 0.75])
parser.add_argument("--tol", type=float, default=1e-3)
parser.add_argument("--seconds", type=float, default=4.0)
parser.add_argument("--no-link-collisions", action="store_true")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
app = AppLauncher(args).app

import torch
from pxr import Usd, UsdGeom, UsdPhysics

from isaaclab.scene import InteractiveSceneCfg
from isaaclab.utils import configclass
from matterix.envs import MatterixBaseEnv, MatterixBaseEnvCfg
from matterix_assets.labware.beakers import BEAKER_500ML_INST_CFG

cfg_file, cfg_class = args.cfg.rsplit(":", 1)
spec = importlib.util.spec_from_file_location("asset_cfg", cfg_file)
module = importlib.util.module_from_spec(spec)
sys.modules["asset_cfg"] = module  # configclass (dataclasses) resolves annotations through sys.modules
spec.loader.exec_module(module)
asset_cfg = getattr(module, cfg_class)(pos=(0.0, 0.0, 0.0))

usd = Usd.Stage.Open(asset_cfg.spawn.usd_path)
top = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(usd.GetDefaultPrim()).ComputeAlignedRange().GetMax()[2]
if args.no_link_collisions:
    geometry = str(usd.GetDefaultPrim().GetPath().AppendChild("Geometry"))
    for p in usd.Traverse():
        if p.HasAPI(UsdPhysics.CollisionAPI) and not str(p.GetPath()).startswith(geometry):
            UsdPhysics.CollisionAPI(p).CreateCollisionEnabledAttr(False)
    asset_cfg.spawn.usd_path = str(Path(tempfile.mkdtemp()) / "no_link_collisions.usdc")
    usd.Export(asset_cfg.spawn.usd_path)


@configclass
class CheckCfg(MatterixBaseEnvCfg):
    env_spacing = 4.0
    scene = InteractiveSceneCfg(num_envs=2, env_spacing=4.0)
    record_path = None
    objects = {"asset": asset_cfg, "probe": BEAKER_500ML_INST_CFG(pos=(0.0, 0.0, top + 0.3))}


env = MatterixBaseEnv(CheckCfg())
env.reset()
asset, probe = env.scene["asset"], env.scene["probe"]
lo, hi = asset.data.joint_pos_limits[..., 0], asset.data.joint_pos_limits[..., 1]
target = torch.stack([lo[i] + f * (hi[i] - lo[i]) for i, f in enumerate(args.fractions)])
action = torch.zeros(env.num_envs, 0, device=env.device)
for _ in range(int(args.seconds * 60)):  # Matterix default 60 Hz control step
    asset.set_joint_position_target(target)
    env.step(action)
err = (asset.data.joint_pos - target).abs()
names = asset.joint_names
worst = err.max(dim=0).values
result = {
    "cfg": args.cfg, "usd": asset_cfg.spawn.usd_path, "noLinkCollisions": args.no_link_collisions,
    "numEnvs": env.num_envs, "numJoints": len(names), "bodies": len(asset.body_names),
    "maxJointErrorM": err.max().item(), "worstJoint": names[int(worst.argmax())],
    "failingJoints": {n: round(worst[i].item(), 5) for i, n in enumerate(names) if worst[i] >= args.tol},
    "targets": {n: target[:, i].tolist() for i, n in enumerate(names)},
    "reached": {n: asset.data.joint_pos[:, i].tolist() for i, n in enumerate(names)},
    "rootDriftM": (asset.data.root_pos_w - env.scene.env_origins).norm(dim=-1).tolist(),
    "assetTopZ": top, "probeRestZ": (probe.data.root_pos_w - env.scene.env_origins)[:, 2].tolist(),
}
result["pass"] = (result["maxJointErrorM"] < args.tol and max(result["rootDriftM"]) < 1e-4
                  and min(result["probeRestZ"]) > top - 0.05)
Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1))
print("VALIDATION", json.dumps({k: result[k] for k in ("numJoints", "bodies", "maxJointErrorM", "worstJoint",
                                                       "failingJoints", "rootDriftM", "probeRestZ", "pass")},
                               ensure_ascii=False), flush=True)
env.close()
app.close()
