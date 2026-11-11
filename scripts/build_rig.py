"""Kinematics from CAD mates: links and prismatic joints (rig.json) from a matterix-sw-export-v1 JSON.

    python build_rig.py <export.json> <overrides.json> <rig.json>

1. Every mate is linearised into twist constraints (mate_dof.mate_constraints, all parts free).
   Its null space N is every motion the mates allow. Welds from the overrides add rigid rows,
   "drop" mates are ignored.
2. Each part-to-part limit-distance mate with travel is a candidate joint coordinate (its distance
   rate). Limits whose rates are parallel over N measure the same joint and are grouped.
   A limit that the mates lock is freed by dropping the "parking" rows (distance mates, mates to a
   sub-assembly's own planes) that stop it, iteratively; the dropped rows are reported.
3. For joint k the smoothest allowed motion (mate-weighted Laplacian) with q_k' = 1, the other joints
   still and the parent side pinned is solved. The parent side is the module stator (part name starts
   with 主体) when the limit names one, else the slower side.
4. Bodies that move with the child side of exactly the same joints form one link (binary signature).

Overrides (all keys optional): {"weld": [[A, B or "<ground>", evidence]],
"drop": [[mate feature, mate owner, evidence]], "names": [[substring of limit owner, joint base name]],
"stator_prefixes": [leaf-name prefixes of module stators, default ["主体"]]}.
Problems (orphan joints, parent mismatch) are listed in rig.json "problems"; fix them with overrides.
Runtime ~3 min for ~1000 parts / 1700 mates (dense SVD).
"""
import json
import sys
from collections import defaultdict

import numpy as np

from mate_dof import GROUND, mate_constraints, rows_pair, trans_row

data = json.load(open(sys.argv[1], encoding="utf-8-sig"))
OVERRIDES = json.load(open(sys.argv[2], encoding="utf-8"))
WELDS = OVERRIDES.get("weld", [])
DROPS = OVERRIDES.get("drop", [])
NAMES = OVERRIDES.get("names", [])
STATORS = OVERRIDES.get("stator_prefixes", ["主体"])  # leaf-name prefixes of module stators (parent side)
DROP_MATES = {i for i, m in enumerate(data["mates"]) if [m["feature"], m["owner"]] in [d[:2] for d in DROPS]}
assert len(DROP_MATES) == len(DROPS), "a drop entry matches no mate (feature, owner)"


def module_name(owner):
    leaf = owner.split("/")[-1]
    return next((name for key, name in NAMES if key in leaf), "joint")


RANK_TOL = 1e-7  # relative; near-redundant CAD mates otherwise read as locks


def assemble(drop):
    comps, _, equations, coupled, limits, skipped = mate_constraints(data, all_flexible=True, drop=drop)
    equations = [e for e in equations if e[3] not in DROP_MATES]
    for a, b, _ in WELDS:  # documented topology facts: rigid between the two parts
        p = np.array(comps[a]["transform"][9:12])  # b may be "<ground>"
        equations = equations + [(a, b, r, -1) for r in rows_pair({"kind": "frame", "p": p}, {"kind": "frame", "p": p})]
    bodies = sorted(comps)
    index = {b: i for i, b in enumerate(bodies)}
    ncol = 6 * len(bodies)

    def pair_row(a, b, r):
        x = np.zeros(ncol)
        if a != GROUND:
            x[6 * index[a]:6 * index[a] + 6] += r
        if b != GROUND:
            x[6 * index[b]:6 * index[b] + 6] -= r
        return x

    rows = [pair_row(a, b, r) for a, b, r, _ in equations]
    for terms, s, rs in coupled:
        x = np.zeros(ncol)
        for body, r in terms.items():
            if body != GROUND:
                x[6 * index[body]:6 * index[body] + 6] += r
        if s != GROUND:
            x[6 * index[s]:6 * index[s] + 6] += rs
        rows.append(x)
    J = np.array(rows)
    _, sv, vt = np.linalg.svd(J, full_matrices=True)
    N = vt[int((sv > RANK_TOL * sv[0]).sum()):].T  # orthonormal basis of allowed motions
    return comps, equations, coupled, limits, skipped, bodies, index, ncol, pair_row, J, N


def limit_rate_row(l, pair_row):
    a, b = l["a"], l["b"]
    plane = a if a["kind"] == "plane" else b  # the distance is measured along the plane normal
    n = plane["d"]
    l["sign"] = 1.0 if np.dot(n, a["p"] - b["p"]) >= 0 else -1.0  # distance = sign * n.(pa - pb)
    l["measured"] = abs(float(np.dot(n, a["p"] - b["p"])))
    return l["sign"] * pair_row(l["bodies"][0], l["bodies"][1], trans_row(n, a["p"]))


def is_part_limit(l, comps):
    return l["maximum"] - l["minimum"] > 1e-6 and not any(comps[b]["isAssembly"] for b in l["bodies"] if b != GROUND)


# Mates that park a travelling part at one pose: a mate to a sub-assembly's own reference planes
# (entity not a component) inside that sub-assembly, or a distance mate. Part-to-part width
# mates are real centring and stay. When one of them is
# what stops a limit mate's travel, it is dropped (and reported) so the axis can move.
def parking(m, comps):
    to_own_planes = m["owner"] and any(e["component"] not in comps for e in m["entities"])
    return to_own_planes or m["featureType"] == "MateDistanceDim"


dropped = set()
for _ in range(6):
    comps, equations, coupled, limits, skipped, bodies, index, ncol, pair_row, J, N = assemble(dropped)
    stuck = [l for l in limits if is_part_limit(l, comps) and np.linalg.norm(limit_rate_row(l, pair_row) @ N) < 1e-6]
    new = set()
    M = J.T @ J + 1e-6 * np.eye(ncol)
    for l in stuck:
        g = limit_rate_row(l, pair_row)
        z = np.linalg.solve(M, g)
        x = z / (g @ z)  # least-violating motion with unit travel
        seen = defaultdict(int)
        viol = {}
        for (_, _, _, mi), r in zip(equations, J[:len(equations)] @ x):
            viol[(mi, seen[mi])] = r * r  # row-level: keep a mate's other directions
            seen[mi] += 1
        worst = max(viol.values())
        new |= {key for key, v in viol.items() if key[0] >= 0 and v > 1e-3 * worst and parking(data["mates"][key[0]], comps)}
    if not new - dropped:
        break
    dropped |= new
comps, equations, coupled, limits, skipped, bodies, index, ncol, pair_row, J, N = assemble(dropped)

# ---- joint coordinates from limit mates ---------------------------------------------------------
travel = [l for l in limits if is_part_limit(l, comps)]
frame_limits = [l for l in limits if any(b != GROUND and comps[b]["isAssembly"] for b in l["bodies"])]
for l in travel:
    l["rate"] = limit_rate_row(l, pair_row) @ N
locked = [l for l in travel if np.linalg.norm(l["rate"]) < 1e-6]
active = [l for l in travel if np.linalg.norm(l["rate"]) >= 1e-6]

groups = []  # limits whose rates are parallel over N measure the same joint
for l in active:
    u = l["rate"] / np.linalg.norm(l["rate"])
    for g in groups:
        if abs(float(u @ g["unit"])) > 1 - 1e-6:
            g["limits"].append(l)
            break
    else:
        groups.append({"unit": u, "limits": [l]})
basis, joints_g, dependent = np.zeros((0, N.shape[1])), [], []
for g in groups:
    rep = g["limits"][0]["rate"]
    if np.linalg.matrix_rank(np.vstack([basis, rep]), 1e-6) > len(basis):
        basis = np.vstack([basis, rep])
        joints_g.append(g)
    else:
        dependent.append(g)  # e.g. the second finger of a symmetric gripper

# Smoothest motion of each joint with the others held still: minimise the mate-weighted relative
# twist between neighbouring bodies (and to the ground), so motion happens only across the joint and
# loosely mated bodies follow the side they are mated to most strongly.
weights = defaultdict(float)
for a, b, _, _ in equations:
    weights[(a, b) if a < b else (b, a)] += 1
L = np.zeros((ncol, ncol))
for (a, b), w in weights.items():
    for x in (a, b):
        if x != GROUND:
            i = 6 * index[x]
            L[i:i + 6, i:i + 6] += w * np.eye(6)
    if GROUND not in (a, b):
        i, j = 6 * index[a], 6 * index[b]
        L[i:i + 6, j:j + 6] -= w * np.eye(6)
        L[j:j + 6, i:i + 6] -= w * np.eye(6)
A = N.T @ L @ N + 1e-9 * np.eye(N.shape[1])
K = len(joints_g)
kkt = np.block([[A, basis.T], [basis, np.zeros((K, K))]])
y = np.linalg.solve(kkt, np.vstack([np.zeros((N.shape[1], K)), np.eye(K)]))[:N.shape[1]]
motion = N @ y  # column k: every body's twist per unit q_k

# Parent side of each joint: a module's 主体 (stator) when the limit mate names one, otherwise the
# side the smoothest motion keeps slower. Re-solve with the parent pinned so the motion cannot leak
# to the stator side (the smoothest motion alone sometimes moves the whole carriage instead).
parent_body = []
for k, g in enumerate(joints_g):
    a, b = g["limits"][0]["bodies"]
    stator = [x for x in (a, b) if x.split("/")[-1].startswith(tuple(STATORS))]
    va, vb = motion[6 * index[a]:6 * index[a] + 3, k], motion[6 * index[b]:6 * index[b] + 3, k]
    parent_body.append(stator[0] if len(stator) == 1 else (b if np.linalg.norm(va) >= np.linalg.norm(vb) else a))
    if parent_body[k] == GROUND:
        continue
    P = N[6 * index[parent_body[k]]:6 * index[parent_body[k]] + 6]
    m = np.block([[A, basis.T, P.T], [basis, np.zeros((K, K + 6))], [P, np.zeros((6, K + 6))]])
    rhs = np.zeros(len(m))
    rhs[N.shape[1] + k] = 1
    y[:, k] = np.linalg.lstsq(m, rhs, rcond=None)[0][:N.shape[1]]
motion = N @ y

# Per joint, a body either moves with the child side (1) or not (0).
t_dir, child_body, signature = [], [], {b: [] for b in bodies}
for k, g in enumerate(joints_g):
    a, b = g["limits"][0]["bodies"]
    va, vb = motion[6 * index[a]:6 * index[a] + 3, k], motion[6 * index[b]:6 * index[b] + 3, k]
    c = b if parent_body[k] == a else a
    t = va - vb if c == a else vb - va
    t_dir.append(t)
    child_body.append(c)
    for x in bodies:
        v = motion[6 * index[x]:6 * index[x] + 3, k]
        signature[x].append(int(np.dot(v, t) / np.dot(t, t) > 0.5))

sets = defaultdict(list)
for x in bodies:
    sets[tuple(signature[x])].append(x)
ground_sig = tuple([0] * K)
sets.setdefault(ground_sig, [])

# ---- joints: parent/child, axis, range ---------------------------------------------------------
joints, link_names, counters, problems = [], {ground_sig: "base"}, defaultdict(int), []
for k, g in enumerate(joints_g):
    rep = g["limits"][0]
    child_sig = tuple(signature[child_body[k]])
    par_sig = tuple(v if i != k else 0 for i, v in enumerate(child_sig))
    other = rep["bodies"][1] if child_body[k] == rep["bodies"][0] else rep["bodies"][0]
    if tuple(signature[other]) != par_sig:
        problems.append(f"{rep['feature']} @ {rep['owner']}: parent side signature {signature[other]} != {list(par_sig)}")
    speed = float(np.linalg.norm(t_dir[k]))
    lower, upper = -np.inf, np.inf
    for l in g["limits"]:
        ratio = float(l["rate"] @ y[:, k])  # this limit's distance change per unit q_k
        lo, hi = sorted((l["minimum"] / ratio, l["maximum"] / ratio))
        lower, upper = max(lower, lo), min(upper, hi)
    base = module_name(rep["owner"])
    counters[base] += 1
    name = f"{base}_{counters[base]}"
    link_names[child_sig] = "link_" + name
    joints.append({"name": name, "type": "prismatic", "parentSig": par_sig, "childSig": child_sig,
                   "axis": (t_dir[k] / speed).tolist(), "unitsPerMeter": 1 / speed,
                   "anchor": rep["a"]["p"].tolist(), "lower": lower, "upper": upper,
                   "limitMates": [{"feature": l["feature"], "owner": l["owner"], "value": l["value"],
                                   "measured": l["measured"], "range": [l["minimum"], l["maximum"]]} for l in g["limits"]]})
for j in joints:
    j["parent"] = link_names.get(j.pop("parentSig"), "?")
    j["child"] = link_names[j.pop("childSig")]
    if j["parent"] == "?":
        problems.append(f"{j['name']}: parent link is not the base or another joint's child")
attached = {}


def representative(s):
    return min(sets[s] or ["-"], key=lambda n: (comps.get(n, {}).get("isAssembly", True), n.count("/"), len(n)))


links = [{"name": link_names.get(s, f"unjointed_{i}"), "displayName": representative(s) if s != ground_sig else "fixed base",
          "parts": sorted(n for n in sets[s] if not comps[n]["isAssembly"])} for i, s in enumerate(sets)]
unjointed = [l for l in links if l["name"].startswith("unjointed_")]
rig = {"jointOrder": [module_name(g["limits"][0]["owner"]) + ":" + g["limits"][0]["feature"] + "@" + g["limits"][0]["owner"].split("/")[-1] for g in joints_g],
       "signatures": {b: "".join(map(str, signature[b])) for b in bodies},
       "source": data["assembly"], "exportedAt": data["exportedAt"], "links": links, "joints": joints,
       "lockedLimitMates": [l["feature"] + " @ " + l["owner"] for l in locked],
       "dependentLimitGroups": [[l["feature"] + " @ " + l["owner"] for l in g["limits"]] for g in dependent],
       "welds": WELDS, "droppedMates": DROPS,
       "droppedParkingRows": [f'{data["mates"][i]["feature"]} @ {data["mates"][i]["owner"] or "<root>"} row {k}' for i, k in sorted(dropped)],
       "ignoredFrameLimitMates": [l["feature"] + " @ " + l["owner"] for l in frame_limits], "problems": problems, "skippedMates": dict(skipped)}
json.dump(rig, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
print(f"null-space dof {N.shape[1]}, limit mates {len(travel)} (locked {len(locked)}), joints {K}, "
      f"dependent groups {len(dependent)}, links {len(links)} (unjointed {len(unjointed)}), "
      f"problems {len(problems)}")
