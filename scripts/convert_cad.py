"""Convert a native CAD assembly (SLDASM/SLDPRT, STEP, IGES, CATIA, ...) to a raw USD layer with HOOPS.

Run with the Isaac Sim python (pip install of isaacsim works; no GUI needed):
    python convert_cad.py <assembly file> <out raw.usdc> [--lod 2]

Output keeps the CAD unit (usually mm), Z-up, component display names (= CAD instance names) and
hidden parts as invisible prims; build_static.py normalises it. About 40 s for ~1000 parts.
"""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("cad")
parser.add_argument("out")
parser.add_argument("--lod", type=int, default=2, help="HOOPS tessellation level of detail (0 coarse .. 4 fine)")
args = parser.parse_args()

from isaacsim import SimulationApp

app = SimulationApp({"headless": True})
import omni.kit.app

assert omni.kit.app.get_app().get_extension_manager().set_extension_enabled_immediate("omni.kit.converter.hoops_core", True)
from omni.converter import hoops

p = hoops.Parameters()
p.upAxis = hoops.UpAxis.eZup
p.convertMetadata = True  # keeps CAD file/occurrence names: the link between USD prims and the CAD export
p.convertPhysicsData = True  # per-B-rep volume / centre of mass / inertia
p.filterStyle = hoops.FilterStyle.eHide  # parts hidden in the CAD view stay, but invisible
p.instancingStyle = hoops.InstancingStyle.eNone  # every occurrence its own prim, so parts can move to links
p.tessLOD = args.lod
p.materialType = hoops.MaterialType.ePreviewSurface
out = Path(args.out).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
code, message = hoops.convert(p, str(Path(args.cad).resolve()), str(out))
print("HOOPS", code, message, flush=True)
app.close()
assert code == 0 and out.exists(), (code, message)
