"""Kinematic DOF analysis of the SolidWorks mates exported by the Matterix add-in.

Each rigid body is a part, or a whole sub-assembly when SolidWorks solves it rigid.
Every mate is linearised at the saved pose into equations on body twists (v at the
world origin, w); the null space of the stacked constraint matrix is the set of
motions the mates allow. Bodies whose relative twist vanishes over that null space
are rigidly connected; each remaining group's motion subspace is a mechanism DOF
candidate. Limit-distance mates only restrict range, so they constrain parallelism
but not the travel; their minimum/maximum are travel offsets from the saved pose.

Usage: python mate_dof.py <export.json> <out.json> [--all-flexible]
Also imported by build_rig.py for mate_constraints().
"""
import json
import sys
from collections import Counter, defaultdict

import numpy as np

TOL = 1e-6
GROUND = "<ground>"


def perp(n):
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    t1 = np.cross(n, a)
    t1 /= np.linalg.norm(t1)
    return t1, np.cross(n, t1)


# Row builders: relative twist (A - B); u(x) = v + w x x  ->  coefficient rows on (v, w).
def trans_row(direction, x):
    return np.concatenate([direction, np.cross(x, direction)])  # dir . (v + w x x)


def rot_row(direction):
    return np.concatenate([np.zeros(3), direction])  # dir . w


def rows_pair(a, b, translation=True):
    """Linearised constraint rows for the common two-entity mate relations."""
    if a["kind"] == "frame" or b["kind"] == "frame":
        return [trans_row(v, a["p"]) for v in np.eye(3)] + [rot_row(v) for v in np.eye(3)]
    kinds = {a["kind"], b["kind"]}
    if kinds == {"plane"}:
        n = a["d"]
        return ([trans_row(n, a["p"])] if translation else []) + [rot_row(t) for t in perp(n)]
    if kinds == {"axis"}:
        t1, t2 = perp(a["d"])
        return ([trans_row(t1, a["p"]), trans_row(t2, a["p"])] if translation else []) + [rot_row(t1), rot_row(t2)]
    if kinds == {"plane", "axis"}:
        pl, ax = (a, b) if a["kind"] == "plane" else (b, a)
        n = pl["d"]
        rot = np.concatenate([np.zeros(3), np.cross(ax["d"], n)])  # n . (w x d) = 0
        return ([trans_row(n, ax["p"])] if translation else []) + ([rot] if np.linalg.norm(rot) > TOL else [])
    if kinds == {"plane", "point"}:
        pl, pt = (a, b) if a["kind"] == "plane" else (b, a)
        return [trans_row(pl["d"], pt["p"])] if translation else []
    if kinds == {"axis", "point"}:
        ax, pt = (a, b) if a["kind"] == "axis" else (b, a)
        return [trans_row(t, pt["p"]) for t in perp(ax["d"])] if translation else []
    if kinds == {"point"}:
        return [trans_row(v, a["p"]) for v in np.eye(3)] if translation else []
    raise KeyError(kinds)


def mate_constraints(data, all_flexible=False, relax_distance=False, drop=()):
    """Linearised mates of an export.

    Returns (comps, body_of, equations, coupled, limits, skipped):
      equations: (body_a, body_b, row, mate_index)  row . (twist_a - twist_b) = 0
      coupled:   ({body: row}, plane_body, plane_row)  symmetric mates
      limits:    limit-distance mates with bodies, entity geometry and travel range
    relax_distance drops the offset row of distance mates (they often just park an axis);
    drop is a set of (mate index, row index within that mate) to ignore.
    """
    comps = {c["name"]: c for c in data["components"] if not c["suppressed"]}

    def transform(name):
        a = np.array(comps[name]["transform"])
        return a[:9].reshape(3, 3), a[9:12]  # row-vector convention: x_world = x_local @ R + t

    def body_of(name):
        """Rigid sub-assemblies collapse into one body; flexible ones expose their children."""
        if all_flexible:
            return name
        parts = name.split("/")
        for i in range(1, len(parts)):
            prefix = "/".join(parts[:i])
            if comps[prefix]["isAssembly"] and not comps[prefix].get("flexible"):
                return prefix
        return name

    def entity(e, owner):
        p = e["params"]
        if p is None:
            return None
        pt, d, r = np.array(p[:3]), np.array(p[3:6]), p[6]
        if owner:  # params are expressed in the owning sub-assembly's frame (checked against geometry)
            R, t = transform(owner)
            pt, d = pt @ R + t, d @ R
        code = e["refType"]
        # Reference codes inferred from the data: 0 point, 1 axis/line, 2 face (plane if r = 0,
        # else cylinder), 3/4 reference plane, 11/25 coordinate system.
        if code == 0:
            kind = "point"
        elif code == 1 or (code == 2 and r > 1e-9):
            kind = "axis"
        elif code in (2, 3, 4):
            kind = "plane"
        else:
            kind = "frame"
        name = e["component"]
        body = body_of(name) if name in comps else (body_of(owner) if owner else GROUND)
        n = np.linalg.norm(d)
        return {"kind": kind, "p": pt, "d": d / n if n > 0 else d, "body": body}

    equations, coupled, limits = [], [], []
    skipped = Counter()
    for mi, m in enumerate(data["mates"]):
        if m["suppressed"]:
            continue
        ft, owner = m["featureType"], m["owner"]
        ents = [entity(e, owner) for e in m["entities"]]
        if any(e is None for e in ents):
            skipped[ft + " (no params)"] += 1
            continue
        if ft in ("MateCoincident", "MateConcentric", "MateDistanceDim", "MateParallel", "MateLimitDistanceDim",
                  "MateCoordinate", "MateLock"):
            a, b = ents
            if a["body"] == b["body"]:
                continue
            if ft in ("MateCoordinate", "MateLock"):
                a = dict(a, kind="frame")
            if ft == "MateConcentric" and a["kind"] == "plane" == b["kind"]:
                skipped[ft + " plane-plane"] += 1
                continue
            free = ft in ("MateParallel", "MateLimitDistanceDim") or (relax_distance and ft == "MateDistanceDim")
            equations += [(a["body"], b["body"], r, mi) for r in rows_pair(a, b, translation=not free)]
            if ft == "MateLimitDistanceDim":
                limits.append({"mate": mi, "feature": m["feature"], "owner": owner, "bodies": [a["body"], b["body"]],
                               "a": a, "b": b, "value": m["dimensions"][0]["value"],
                               "minimum": m["minimum"], "maximum": m["maximum"]})
        elif ft == "MateWidth":
            # width faces on one body, tab faces on another: the mid-planes coincide.
            a, b = ents[0], ents[-1]
            if a["body"] == b["body"]:
                continue
            n = a["d"]
            mid_a = np.mean([e["p"] for e in ents if e["body"] == a["body"]], axis=0)
            equations.append((a["body"], b["body"], trans_row(n, mid_a), mi))
            if all(e["kind"] == "plane" for e in ents):
                equations += [(a["body"], b["body"], rot_row(t), mi) for t in perp(n)]
        elif ft == "MateSymmetric":
            # e1 and e2 mirror about plane S: nS.(u1 - uS)(p1) + nS.(u2 - uS)(p2) = 0
            e1, e2, s = ents
            nS = s["d"]
            coupled.append(({e1["body"]: trans_row(nS, e1["p"]), e2["body"]: trans_row(nS, e2["p"])},
                            s["body"], -(trans_row(nS, e1["p"]) + trans_row(nS, e2["p"]))))
        else:
            skipped[ft] += 1
    if drop:
        seen = Counter()
        kept = []
        for eq in equations:
            k = seen[eq[3]]
            seen[eq[3]] += 1
            if (eq[3], k) not in drop:
                kept.append(eq)
        equations = kept
    return comps, body_of, equations, coupled, limits, skipped


def null_space(bodies, equations, coupled):
    index = {b: i for i, b in enumerate(bodies)}
    rows = []
    for a, b, r, _ in equations:
        row = np.zeros(6 * len(bodies))
        if a != GROUND:
            row[6 * index[a]:6 * index[a] + 6] += r
        if b != GROUND:
            row[6 * index[b]:6 * index[b] + 6] -= r
        rows.append(row)
    for terms, s, rs in coupled:
        row = np.zeros(6 * len(bodies))
        for body, r in terms.items():
            if body != GROUND:
                row[6 * index[body]:6 * index[body] + 6] += r
        if s != GROUND:
            row[6 * index[s]:6 * index[s] + 6] += rs
        rows.append(row)
    J = np.array(rows)
    _, sv, vt = np.linalg.svd(J, full_matrices=True)
    rank = int((sv > 1e-8 * sv[0]).sum())
    N = vt[rank:].T
    return {b: N[6 * i:6 * i + 6] for b, i in index.items()}, rank, len(J)


def describe(Tg):
    u, s, _ = np.linalg.svd(Tg)
    modes = []
    for k in range(int((s > 1e-6).sum())):
        v, w = u[:3, k], u[3:, k]
        if np.linalg.norm(w) < 1e-6:
            modes.append({"type": "translation", "dir": np.round(v / np.linalg.norm(v), 4).tolist()})
        else:
            point = np.cross(w, v) / np.dot(w, w)
            modes.append({"type": "rotation", "axis": np.round(w / np.linalg.norm(w), 4).tolist(),
                          "point": np.round(point, 4).tolist(), "pitch": round(float(np.dot(w, v) / np.dot(w, w)), 6)})
    return modes


def main():
    data = json.load(open(sys.argv[1], encoding="utf-8-sig"))
    comps, body_of, equations, coupled, limits, skipped = mate_constraints(data, "--all-flexible" in sys.argv)
    bodies = sorted({b for a, b2, _, _ in equations for b in (a, b2)}
                    | {b for c, s, _ in coupled for b in list(c) + [s]}
                    | {body_of(n) for n in comps if not comps[n]["isAssembly"]})
    bodies = [b for b in bodies if b != GROUND]
    T, rank, neq = null_space(bodies, equations, coupled)
    print(f"bodies {len(bodies)}, equations {neq}, rank {rank}, skipped {dict(skipped)}", flush=True)

    parent = {b: b for b in bodies}

    def find(b):
        while parent[b] != b:
            parent[b] = parent[parent[b]]
            b = parent[b]
        return b

    grounded = {b for b in bodies if np.abs(T[b]).max() < TOL}
    for a, b, _, _ in equations:
        if GROUND not in (a, b) and np.abs(T[a] - T[b]).max() < TOL:
            parent[find(a)] = find(b)
    groups = defaultdict(list)
    for b in bodies:
        groups[find(b)].append(b)
    out = [{"members": sorted(members), "dof": int(np.linalg.matrix_rank(T[root], 1e-6)), "modes": describe(T[root])}
           for root, members in groups.items() if not all(m in grounded for m in members)]
    out.sort(key=lambda g: (-len(g["members"]), g["members"][0]))
    limit_out = [{"feature": l["feature"], "owner": l["owner"], "bodies": l["bodies"], "normal": l["a"]["d"].tolist(),
                  "value": l["value"], "minimum": l["minimum"], "maximum": l["maximum"]} for l in limits]
    json.dump({"bodies": len(bodies), "equations": neq, "rank": rank, "totalDof": 6 * len(bodies) - rank,
               "grounded": sorted(grounded), "movingGroups": out, "limits": limit_out, "skipped": dict(skipped)},
              open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    print(f"grounded bodies {len(grounded)}, moving groups {len(out)}")


if __name__ == "__main__":
    main()
