"""Part names of a static USD (build_static.py output) when there is no CAD export to name them.

A part is addressed by its CAD display-name path below <root>/Geometry, e.g. "asm/Slide-1/Carriage-1".
Siblings with the same display name (common in STEP) get "#2", "#3", ... in USD child order.
"""
from collections import Counter


def named_prims(geometry):
    """{display-name path: prim} for every prim below the Geometry prim."""
    out = {}

    def walk(prim, path):
        seen = Counter()
        for c in prim.GetChildren():
            name = c.GetMetadata("displayName") or c.GetName()  # converters other than HOOPS may not set it
            seen[name] += 1
            q = path + name + (f"#{seen[name]}" if seen[name] > 1 else "")
            out[q] = c
            walk(c, q + "/")

    walk(geometry, "")
    return out
