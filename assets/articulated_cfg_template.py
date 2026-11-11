"""Matterix config for <ASSET NAME> (<ASSET>.usdc), built by the matterix-cad-articulation skill.

<N> prismatic joints from the CAD mates; 0 = CAD saved pose, limits in metres. Main axes: <list>.
"""
from pathlib import Path

import isaaclab.sim as sim_utils
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.utils import configclass
from matterix_assets.matterix_articulation import MatterixArticulationCfg

USD_PATH = str(Path(__file__).resolve().parent / "<ASSET>.usdc")


@configclass
class ASSET_ARTICULATED_INST_CFG(MatterixArticulationCfg):  # rename, e.g. PIPETTING_STATION_ARTICULATED_INST_CFG
    prim_path = MatterixArticulationCfg().prim_path + "_Equipment"
    spawn = sim_utils.UsdFileCfg(
        usd_path=USD_PATH,
        # the asset never collides with itself (see build_articulated.py); root fixed to the world
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(fix_root_link=True, enabled_self_collisions=False),
    )
    init_state = MatterixArticulationCfg.InitialStateCfg(joint_pos={".*": 0.0})
    # shortcut: one stiff position drive for every axis (no motor data); replace per axis with the
    # motor / screw-module ratings when force or speed limits matter. Keep equal to the USD drive gains.
    actuators = {"all": ImplicitActuatorCfg(joint_names_expr=[".*"], stiffness=1e5, damping=3e3)}
    semantic_tags = [("class", "<class name>")]
