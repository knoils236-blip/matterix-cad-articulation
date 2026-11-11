"""Render front and iso previews of a USD asset (Isaac Sim python, headless).

    python render_preview.py <asset.usdc> <out_dir> [--front-axis +Y]

Cameras are placed from the asset's bounding box; --front-axis is the operator side.
Writes <out_dir>/preview_front.png and preview_iso.png. Translucency is on so clear panels show.
"""
import argparse
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("usd")
parser.add_argument("out_dir")
parser.add_argument("--front-axis", default="+Y", choices=["+X", "-X", "+Y", "-Y"])
args = parser.parse_args()

from isaacsim import SimulationApp

app = SimulationApp({"headless": True})
import carb
import omni.replicator.core as rep
import omni.usd
from pxr import Usd, UsdGeom

carb.settings.get_settings().set("/rtx/translucency/enabled", True)
out = Path(args.out_dir).resolve()
omni.usd.get_context().open_stage(str(Path(args.usd).resolve()))
for _ in range(20):
    app.update()
stage = omni.usd.get_context().get_stage()
r = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(stage.GetDefaultPrim()).ComputeAlignedRange()
c, size = (r.GetMin() + r.GetMax()) / 2, max(r.GetMax() - r.GetMin())
sign, axis = (1 if args.front_axis[0] == "+" else -1), "XY".index(args.front_axis[1])
front = [c[0], c[1], c[2]]
front[axis] += sign * 2.2 * size
side = [c[0], c[1], c[2] + size]
side[axis] += sign * 1.6 * size
side[1 - axis] += 1.6 * size

rep.create.light(light_type="dome", intensity=1000)
for name, eye in {"front": front, "iso": side}.items():
    camera = rep.create.camera(position=tuple(eye), look_at=tuple(c))
    product = rep.create.render_product(camera, (1280, 960))
    writer = rep.WriterRegistry.get("BasicWriter")
    tmp = out / f"_render_{name}"
    writer.initialize(output_dir=str(tmp), rgb=True)
    writer.attach([product])
    for _ in range(3):
        rep.orchestrator.step(rt_subframes=16)
    writer.detach()
    rep.orchestrator.wait_until_complete()
    sorted(tmp.glob("rgb_*.png"))[-1].replace(out / f"preview_{name}.png")
    shutil.rmtree(tmp)
app.close()
