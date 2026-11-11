"""rig.json + the static USD (build_static.py) [+ the CAD export] -> one articulated USD.

    python build_articulated.py --rig <rig.json> --static <static.usdc> --out <out.usdc> [--export <export.json>]
        [--stiffness 1e5] [--damping 3e3] [--max-force 1e5] [--density "6061 铝合金=2700" ...]

With --export the rig comes from build_rig.py (CAD frame, part names = export component names).
Without it the rig is hand-written (references/manual-rig.md): part names are display-name paths
below Geometry (list_components.py <static.usdc>), a name of a sub-assembly moves the whole
sub-assembly, axis/anchor are in the static USD frame (metres), revolute limits in radians, and
every link states its "mass" (kg) or "density" (kg/m3); PhysX derives COM/inertia from the hulls.

MATTERIX Methods (Asset generation): an articulated asset carries links, joints and mass properties
so workflow skills can drive its devices. Here:
  * every part of a moving link is moved out of the static geometry under its link rigid body at its
    CAD pose; the CAD frame must equal the USD frame up to a translation (asserted on every part);
  * moving parts collide as convex hulls (dynamic bodies cannot use triangle meshes); everything
    else stays a static triangle-mesh collider;
  * the asset never collides with itself: links among themselves via enabled_self_collisions=False
    in the Matterix cfg, links vs static geometry via per-link FilteredPairs over the static
    colliders inside the link's swept box (a collision group cannot be used: Isaac Lab already puts
    each env in one; filtered pairs on the articulation root only cover the root link);
  * link mass/COM/inertia are summed from the CAD part mass properties; --density fixes parts whose
    CAD material is unset but whose custom property (材料/材质) names it;
  * prismatic joints with the mate-derived axis and travel, zero at the CAD saved pose, with a
    linear position drive (same gains as the cfg, so the asset also holds pose in plain Isaac Sim).
The base link is a massed anchor without geometry carrying ArticulationRootAPI (Isaac Lab's
fix_root_link needs the root on a rigid body); the Matterix cfg fixes it to the world.
Writes <out>.report.json.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

parser = argparse.ArgumentParser()
parser.add_argument("--export")
parser.add_argument("--rig", required=True)
parser.add_argument("--static", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--stiffness", type=float, default=1e5)
parser.add_argument("--damping", type=float, default=3e3)
parser.add_argument("--max-force", type=float, default=1e5)
parser.add_argument("--density", nargs="*", default=[], help='material property value=kg/m3, e.g. "6061 铝合金=2700"')
args = parser.parse_args()
OUT = Path(args.out).resolve()
REPORT = Path(str(OUT) + ".report.json")
DENSITY_BY_PROPERTY = {k: float(v) for k, v in (d.rsplit("=", 1) for d in args.density)}

rig = json.load(open(args.rig, encoding="utf-8"))

layer = Sdf.Layer.CreateAnonymous(".usdc")
layer.TransferContent(Sdf.Layer.FindOrOpen(str(Path(args.static).resolve())))
stage = Usd.Stage.Open(layer)
station = stage.GetDefaultPrim()
geometry = stage.GetPrimAtPath(station.GetPath().AppendChild("Geometry"))
xc = UsdGeom.XformCache()
prim_of, assumed = {}, {}

if args.export:
    data = json.load(open(args.export, encoding="utf-8-sig"))
    comps = {c["name"]: c for c in data["components"] if not c["suppressed"]}
    massprops = {(p["path"], p["config"]): p for p in data["parts"]}
    # Geometry/<raw layer root>/<top assembly>: HOOPS puts the active configuration under the raw root.
    top = geometry.GetChildren()[0].GetChildren()[0]

    def walk(prim, path):
        for c in prim.GetChildren():
            q = f"{path}/{c.GetMetadata('displayName')}" if path else c.GetMetadata("displayName")
            if q in comps:
                prim_of[q] = c
                walk(c, q)

    walk(top, "")
    assert len(prim_of) == len(comps), (len(prim_of), len(comps))
    # SolidWorks frame -> station frame: pure translation, measured on every part.
    offsets = []
    for n, prim in prim_of.items():
        if not comps[n]["isAssembly"]:
            offsets.append(np.array(xc.GetLocalToWorldTransform(prim))[3, :3] - np.array(comps[n]["transform"][9:12]))
    offsets = np.array(offsets)
    SHIFT = offsets.mean(axis=0)
    assert np.abs(offsets - SHIFT).max() < 1e-6, f"CAD frame is not a pure translation of the USD frame ({np.abs(offsets - SHIFT).max()} m): add the rotation"
else:
    from usd_tree import named_prims

    prim_of = named_prims(geometry)
    SHIFT = np.zeros(3)  # a hand-written rig is already in the static USD frame
    missing = [p for l in rig["links"] for p in l["parts"] if p not in prim_of]
    assert not missing, f"rig parts not in the static USD (see list_components.py): {missing}"


def part_mass(name):
    c = comps[name]
    p = massprops[(c["path"], c["config"])]
    m, inertia = p["mass"], np.array(p["inertiaAtCom"]).reshape(3, 3)
    named = p["configProperties"].get("材料") or p["configProperties"].get("材质") or p["properties"].get("材料")
    if not p["material"] and named in DENSITY_BY_PROPERTY:
        k = DENSITY_BY_PROPERTY[named] / p["density"]
        m, inertia = m * k, inertia * k
    elif not p["material"] or m <= 0:  # mass below is a guess (water): report it so it can be fixed with --density
        a = assumed.setdefault(c["path"].replace("\\", "/").split("/")[-1], {"namedMaterial": named, "instances": 0, "massKg": 0.0})
        a["instances"] += 1
        a["massKg"] = round(a["massKg"] + (m if m > 0 else p["volume"] * 1000.0), 5)
    if m <= 0:  # 3 parts export density 0; treat them like the other unspecified parts (water)
        m, inertia = p["volume"] * 1000.0, np.zeros((3, 3))
    t = np.array(c["transform"])
    R = t[:9].reshape(3, 3)  # row-vector convention: x_world = x_local @ R + t
    com = np.array(p["centerOfMass"]) @ R + t[9:12] + SHIFT
    return m, com, R.T @ inertia @ R


def link_mass(parts):
    items = [part_mass(n) for n in parts]
    m = sum(i[0] for i in items)
    com = sum(i[0] * i[1] for i in items) / m
    inertia = np.zeros((3, 3))
    for mi, ci, Ii in items:
        d = ci - com
        inertia += Ii + mi * (d @ d * np.eye(3) - np.outer(d, d))
    w, v = np.linalg.eigh(inertia)
    if np.linalg.det(v) < 0:
        v[:, 0] *= -1
    q = Gf.Matrix3d(*v.T.flatten().tolist()).ExtractRotation().GetQuat()  # rows = principal axes
    return m, com, np.maximum(w, 1e-9), q


def set_mass(prim, m, com, diag, quat):
    api = UsdPhysics.MassAPI.Apply(prim)
    api.CreateMassAttr(float(m))
    api.CreateCenterOfMassAttr(Gf.Vec3f(*com.tolist()))
    api.CreateDiagonalInertiaAttr(Gf.Vec3f(*diag.tolist()))
    api.CreatePrincipalAxesAttr(Gf.Quatf(quat))


# ---- links -------------------------------------------------------------------------------------
base = UsdGeom.Xform.Define(stage, station.GetPath().AppendChild("base")).GetPrim()
UsdPhysics.RigidBodyAPI.Apply(base)
set_mass(base, 1.0, np.zeros(3), np.full(3, 1e-3), Gf.Quatd(1, 0, 0, 0))  # anchor only, fixed to world
link_path = {"base": base.GetPath()}
moves, report_links = [], []
for link in rig["links"]:
    if link["name"] in ("base",) or not link["parts"]:
        continue
    assert not link["name"].startswith("unjointed_"), link["name"]
    prim = UsdGeom.Xform.Define(stage, station.GetPath().AppendChild(link["name"])).GetPrim()
    UsdPhysics.RigidBodyAPI.Apply(prim)
    if args.export:
        m, com, diag, quat = link_mass(link["parts"])
        set_mass(prim, m, com, diag, quat)
        report_links.append({"name": link["name"], "parts": len(link["parts"]), "mass": round(m, 4), "com": com.round(4).tolist()})
    else:  # exactly one of mass / density, from a datasheet or the material; COM and inertia from the colliders
        (key,) = {"mass", "density"} & link.keys()
        api = UsdPhysics.MassAPI.Apply(prim)
        (api.CreateMassAttr if key == "mass" else api.CreateDensityAttr)(float(link[key]))
        report_links.append({"name": link["name"], "parts": len(link["parts"]), key: link[key]})
    link_path[link["name"]] = prim.GetPath()
    for i, part in enumerate(link["parts"]):
        src = prim_of[part]
        moves.append((src.GetPath(), prim.GetPath().AppendChild(f"part_{i}"), xc.GetLocalToWorldTransform(src),
                      UsdGeom.Imageable(src).ComputeVisibility() == UsdGeom.Tokens.invisible))

hulls = 0
for src, dst, world, hidden in moves:
    assert Sdf.CopySpec(layer, src, layer, dst)
    prim = stage.GetPrimAtPath(dst)
    xf = UsdGeom.Xformable(prim)
    for op in xf.GetOrderedXformOps():
        prim.RemoveProperty(op.GetOpName())
    xf.ClearXformOpOrder()
    xf.AddTransformOp().Set(world)  # link frames are the station frame at the CAD pose
    if hidden:
        UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
    for other, _, _, _ in moves:  # a nested part that belongs to another link leaves this copy
        if other != src and other.HasPrefix(src):
            stage.RemovePrim(other.ReplacePrefix(src, dst))
    for p in Usd.PrimRange(prim):
        if p.HasAPI(UsdPhysics.MeshCollisionAPI):
            UsdPhysics.MeshCollisionAPI(p).GetApproximationAttr().Set(UsdPhysics.Tokens.convexHull)
            hulls += 1
for src, _, _, _ in moves:
    stage.RemovePrim(src)

# ---- joints ------------------------------------------------------------------------------------
UsdGeom.Scope.Define(stage, station.GetPath().AppendChild("joints"))
for j in rig["joints"]:
    revolute = j["type"] == "revolute"
    assert revolute or j["type"] == "prismatic", j["type"]
    k = 180 / np.pi if revolute else 1.0  # USD angular limits and gains are per degree, the rig is in radians
    joint = (UsdPhysics.RevoluteJoint if revolute else UsdPhysics.PrismaticJoint).Define(
        stage, station.GetPath().AppendPath(f"joints/{j['name']}"))
    joint.CreateBody0Rel().SetTargets([link_path[j["parent"]]])
    joint.CreateBody1Rel().SetTargets([link_path[j["child"]]])
    anchor = Gf.Vec3f(*(np.array(j["anchor"]) + SHIFT).tolist())
    rot = Gf.Quatf(Gf.Rotation(Gf.Vec3d(1, 0, 0), Gf.Vec3d(*j["axis"])).GetQuat())  # joint X = travel axis
    for pos, ori in ((joint.CreateLocalPos0Attr, joint.CreateLocalRot0Attr), (joint.CreateLocalPos1Attr, joint.CreateLocalRot1Attr)):
        pos(anchor)
        ori(rot)
    joint.CreateAxisAttr(UsdPhysics.Tokens.x)
    joint.CreateLowerLimitAttr(float(j["lower"] * k))
    joint.CreateUpperLimitAttr(float(j["upper"] * k))
    drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), UsdPhysics.Tokens.angular if revolute else UsdPhysics.Tokens.linear)
    drive.CreateTypeAttr(UsdPhysics.Tokens.force)
    drive.CreateStiffnessAttr(args.stiffness / k)
    drive.CreateDampingAttr(args.damping / k)
    drive.CreateMaxForceAttr(args.max_force)

UsdPhysics.ArticulationRootAPI.Apply(base)  # Isaac Lab's fix_root_link needs the root on a rigid body
# The station never collides with itself: CAD parts touch at rails and guides and the joint limits
# bound the travel. A collision group cannot do this (Isaac Lab already puts each env in one) and
# filtered pairs on the articulation root do not reach the other links (measured), so every moving
# link filters the static colliders inside its swept box: its box grown by the travel of every joint
# from the base to it (a revolute joint grows it to the cube around the sphere it can sweep). Links among themselves: enabled_self_collisions=False in the cfg.
bbox = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
static = [(p.GetPath(), bbox.ComputeWorldBound(p).ComputeAlignedRange())
          for p in Usd.PrimRange(geometry) if p.HasAPI(UsdPhysics.CollisionAPI)]
s_lo = np.array([list(r.GetMin()) for _, r in static])
s_hi = np.array([list(r.GetMax()) for _, r in static])
joint_to = {j["child"]: j for j in rig["joints"]}
filtered = 0
for name, path in link_path.items():
    if name == "base":
        continue
    r = bbox.ComputeWorldBound(stage.GetPrimAtPath(path)).ComputeAlignedRange()
    lo, hi = np.array(list(r.GetMin())), np.array(list(r.GetMax()))
    j = joint_to[name]
    while True:  # Minkowski sum with each joint's travel segment
        if j["type"] == "revolute":
            a = np.array(j["anchor"]) + SHIFT
            reach = np.linalg.norm(np.maximum(np.abs(lo - a), np.abs(hi - a)))
            lo, hi = np.minimum(lo, a - reach), np.maximum(hi, a + reach)
        else:
            ends = np.outer([j["lower"], j["upper"]], j["axis"])
            lo, hi = lo + ends.min(axis=0).clip(max=0), hi + ends.max(axis=0).clip(min=0)
        if j["parent"] == "base":
            break
        j = joint_to[j["parent"]]
    hit = np.all((s_lo <= hi + 1e-3) & (s_hi >= lo - 1e-3), axis=1)
    UsdPhysics.FilteredPairsAPI.Apply(stage.GetPrimAtPath(path)).CreateFilteredPairsRel().SetTargets(
        [static[i][0] for i in np.flatnonzero(hit)])
    filtered += int(hit.sum())

stage.Flatten().Export(str(OUT))
REPORT.write_text(json.dumps({
    "source": rig.get("source"), "swToStationShift": SHIFT.round(6).tolist(),
    "joints": [{k: j[k] for k in ("name", "type", "parent", "child", "axis", "lower", "upper")} for j in rig["joints"]],
    "links": report_links,
    # moving parts without a CAD material: mass = volume x 1000 kg/m3, a guess. Fix with --density when
    # namedMaterial is set, otherwise ask for the material or list them under the asset's limits.
    "assumedWaterDensityParts": assumed, "assumedWaterDensityMassKg": round(sum(a["massKg"] for a in assumed.values()), 4), "movedParts": len(moves), "convexHullColliders": hulls, "filteredStaticPairs": filtered,
}, ensure_ascii=False, indent=1))
print(f"links {len(report_links)} + base, joints {len(rig['joints'])}, moved parts {len(moves)}, hulls {hulls}, "
      f"guessed-density part files {len(assumed)} ({sum(a['massKg'] for a in assumed.values()):.3f} kg) -> {OUT.name}")
