"""Print a rig.json as a joint tree, plus everything that blocks a clean build.

    python show_rig.py <rig.json> [--hide PREFIX ...] [--body SUBSTRING ...]

--hide skips joints whose name starts with PREFIX under the base (e.g. syringe_plunger: many
identical plungers); --body prints which joints move the matching bodies (signature bits), the
fastest way to see why a part lands in the wrong link.
"""
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument("rig")
parser.add_argument("--hide", nargs="*", default=[])
parser.add_argument("--body", nargs="*", default=[])
args = parser.parse_args()
r = json.load(open(args.rig, encoding="utf-8"))
links = {l["name"]: l for l in r["links"]}
kids = {}
for j in r["joints"]:
    kids.setdefault(j["parent"], []).append(j)


def show(link, depth=0):
    for j in kids.get(link, []):
        hidden = depth == 0 and j["name"].startswith(tuple(args.hide)) if args.hide else False
        child = links[j["child"]]
        if not hidden:
            print("  " * depth + f"{j['name']:20s} axis={[round(v, 2) for v in j['axis']]} "
                  f"[{j['lower'] * 1000:.1f}, {j['upper'] * 1000:.1f}] mm  parts={len(child['parts'])}  "
                  f"「{child['displayName'].split('/')[-1][:30]}」 limits={[m['feature'] for m in j['limitMates']]}")
        show(j["child"], depth + 1)


print(f"base parts {len(links['base']['parts'])}, joints {len(r['joints'])}, links {len(r['links'])}")
show("base")
orphans = [j for j in r["joints"] if j["parent"] not in links]
for j in orphans:
    print("ORPHAN", j["name"], "child parts", len(links[j["child"]]["parts"]),
          [m["feature"] + "@" + m["owner"].split("/")[-1] for m in j["limitMates"]])
unjointed = [(l["name"], len(l["parts"]), l["displayName"]) for l in r["links"] if l["name"].startswith("unjointed_")]
print("unjointed links (0 parts = harmless sub-assembly node):", unjointed)
print("locked limit mates:", len(r["lockedLimitMates"]), " dropped parking rows:", len(r["droppedParkingRows"]))
for p in r["problems"]:
    print("PROBLEM", p[:200])
order = r["jointOrder"]
for b, sig in r["signatures"].items():
    if any(s in b for s in args.body):
        print("BODY", b, "moves with", [order[i] for i, c in enumerate(sig) if c == "1"])
clean = not r["problems"] and not orphans and all(n == 0 for _, n, _ in unjointed)
print("CLEAN" if clean else "NOT CLEAN")
