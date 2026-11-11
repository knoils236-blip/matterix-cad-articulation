"""List components of a CAD export with their CAD-frame position (mm), to spot coincident mounts.

    python list_components.py <export.json | static.usdc> [--under PREFIX] [--depth 2] [--grep SUBSTRING ...]

Given a static USD (no CAD export: STEP etc.) it lists the part names a hand-written rig uses, with
the bounding-box centre and size in the USD frame (mm).

A bracket whose x/z equals a slider's x/z is very likely bolted to that slider: that is the
geometric evidence behind a weld when the mates leave ownership open. Confirm with the user.
"""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("export")
parser.add_argument("--under", default="")
parser.add_argument("--depth", type=int, default=2)
parser.add_argument("--grep", nargs="*", default=[])
args = parser.parse_args()
if not args.export.endswith(".json"):
    from pxr import Usd, UsdGeom

    from usd_tree import named_prims

    stage = Usd.Stage.Open(args.export)
    box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    for n, prim in named_prims(stage.GetPrimAtPath(stage.GetDefaultPrim().GetPath().AppendChild("Geometry"))).items():
        leaf = n.split("/")[-1]  # --grep matches the leaf name here: every path contains its ancestors' names
        if n.startswith(args.under) and n.count("/") - args.under.count("/") < args.depth and (not args.grep or any(g in leaf for g in args.grep)):
            r = box.ComputeWorldBound(prim).ComputeAlignedRange()
            if r.IsEmpty():  # materials and other prims without geometry
                continue
            hidden = UsdGeom.Imageable(prim).ComputeVisibility() == UsdGeom.Tokens.invisible
            print(n, "centre", [round(v * 1000, 1) for v in r.GetMidpoint()], "size", [round(v * 1000, 1) for v in r.GetSize()],
                  "(hidden)" if hidden else "")
    raise SystemExit
data = json.load(open(args.export, encoding="utf-8-sig"))
base = args.under.count("/") + (1 if args.under else 0)
for c in data["components"]:
    n = c["name"]
    if c["suppressed"] or not n.startswith(args.under) or n.count("/") - base >= args.depth:
        continue
    if args.grep and not any(g in n for g in args.grep):
        continue
    t = [round(v * 1000, 1) for v in c["transform"][9:12]]
    print(("A " if c["isAssembly"] else "  ") + n, t, "" if c["visible"] else "(hidden)")
