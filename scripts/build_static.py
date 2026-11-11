"""Normalise a raw HOOPS layer into a static, Matterix-ready USD (plain pxr, no Isaac Sim needed).

    python build_static.py <raw.usdc> <out.usdc> [--root Station] [--unhide NAME ...]
                           [--clear NAME_SUBSTRING ... [--clear-exclude SUBSTRING ...]]

* metres, Z-up, defaultPrim /<root>, origin at the floor centre of the visible footprint;
* --unhide: sub-assemblies (CAD display names) the CAD working view hides but that physically exist;
* --clear: parts whose display name contains the substring get a clear PMMA-like material;
* every visible mesh becomes a static triangle-mesh collider, one physics material (friction 0.5,
  restitution 0: no CAD data, PhysX-typical values); hidden meshes keep no collider;
* flattened to one self-contained usdc; <out>.report.json holds the statistics.
"""
import argparse
import json
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

parser = argparse.ArgumentParser()
parser.add_argument("raw")
parser.add_argument("out")
parser.add_argument("--root", default="Station")
parser.add_argument("--unhide", nargs="*", default=[])
parser.add_argument("--clear", nargs="*", default=[])
parser.add_argument("--clear-exclude", nargs="*", default=[])
args = parser.parse_args()
raw_path, out = Path(args.raw).resolve(), Path(args.out).resolve()

raw = Usd.Stage.Open(str(raw_path))
raw_root = raw.GetDefaultPrim()
mpu = UsdGeom.GetStageMetersPerUnit(raw)
assert UsdGeom.GetStageUpAxis(raw) == UsdGeom.Tokens.z, UsdGeom.GetStageUpAxis(raw)

stage = Usd.Stage.CreateInMemory()
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
root = UsdGeom.Xform.Define(stage, f"/{args.root}")
stage.SetDefaultPrim(root.GetPrim())
geometry = UsdGeom.Xform.Define(stage, f"/{args.root}/Geometry")
geometry.GetPrim().GetReferences().AddReference(str(raw_path), raw_root.GetPath())

unhidden = []
for prim in Usd.PrimRange(geometry.GetPrim()):
    if prim.GetMetadata("displayName") in args.unhide:
        unhidden.append(prim.GetMetadata("displayName"))
        for p in Usd.PrimRange(prim):
            if p.IsA(UsdGeom.Imageable):
                UsdGeom.Imageable(p).CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
assert sorted(set(unhidden)) == sorted(set(args.unhide)), (unhidden, args.unhide)

# Footprint of what will be shown (after unhiding), in raw units.
box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
r = box.ComputeWorldBound(geometry.GetPrim()).ComputeAlignedRange()
lo, hi = r.GetMin(), r.GetMax()
shift = Gf.Vec3d(-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])
geometry.ClearXformOpOrder()  # the referenced raw root may carry its own ops
geometry.AddScaleOp().Set(Gf.Vec3f(mpu, mpu, mpu))
geometry.AddTranslateOp().Set(shift)  # applied first (raw units), then scaled to metres

material = UsdShade.Material.Define(stage, f"/{args.root}/PhysicsMaterials/Default")
pm = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
pm.CreateStaticFrictionAttr(0.5)
pm.CreateDynamicFrictionAttr(0.5)
pm.CreateRestitutionAttr(0.0)

clear = []
if args.clear:
    glass = UsdShade.Material.Define(stage, f"/{args.root}/Looks/Clear")
    shader = UsdShade.Shader.Define(stage, f"/{args.root}/Looks/Clear/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.85, 0.92, 0.95))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.15)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.05)
    shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.49)
    glass.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    for prim in Usd.PrimRange(geometry.GetPrim()):
        name = prim.GetMetadata("displayName") or ""
        if any(s in name for s in args.clear) and not any(s in name for s in args.clear_exclude):
            clear.append(name)
            for mesh in Usd.PrimRange(prim):
                if mesh.IsA(UsdGeom.Mesh):
                    UsdShade.MaterialBindingAPI.Apply(mesh).Bind(glass)

colliders = hidden = triangles = 0
for prim in Usd.PrimRange(geometry.GetPrim()):
    if not prim.IsA(UsdGeom.Mesh):
        continue
    if UsdGeom.Imageable(prim).ComputeVisibility() == UsdGeom.Tokens.invisible:
        hidden += 1  # hidden CAD bodies (alternates, old revisions) stay for display toggling only
        continue
    UsdPhysics.CollisionAPI.Apply(prim)
    UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr(UsdPhysics.Tokens.none)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material, UsdShade.Tokens.weakerThanDescendants, "physics")
    colliders += 1
    triangles += len(UsdGeom.Mesh(prim).GetFaceVertexCountsAttr().Get() or [])

stage.Flatten().Export(str(out))
report = {
    "raw": str(raw_path), "rawMetersPerUnit": mpu, "originShiftRawUnits": list(shift),
    "sizeMeters": [round((hi[i] - lo[i]) * mpu, 4) for i in range(3)], "unhidden": unhidden, "clearParts": clear,
    "colliderMeshes": colliders, "colliderTriangles": triangles, "hiddenMeshesWithoutCollider": hidden,
}
Path(str(out) + ".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False))
