"""References that match no box exactly, grouped by slice: the merge step's to-do list.

usage: python3 -I pipeline/refs.py MAP_DIR [--family ep:] [--limit 25]

The build resolves a missing reference by falling back to its file, folder or owning group, which is
right for a function nobody gave a box. It is wrong for an endpoint (often a route no server
declares, which deserves its own inferred box), a flow step (the camera needs a real box), or a
group id from another slice (validate it there, then retarget). Read this after the agents finish.
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("map_dir")
    ap.add_argument("--family", help="only references starting with this, e.g. ep: or FLOWSTEP")
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args()
    parts = {os.path.basename(f): json.load(open(f)) for f in sorted(glob.glob(os.path.join(a.map_dir, "parts", "*.json")))}
    if not parts:
        sys.exit(f"refs: no slices in {os.path.join(a.map_dir, 'parts')}; copy them there first")
    skeleton = json.load(open(os.path.join(a.map_dir, "skeleton.json")))
    ids = {n["id"] for n in skeleton["nodes"]} | {n["id"] for d in parts.values() for n in d["nodes"]}
    flows_path = os.path.join(a.map_dir, "flows.json")
    docs = list(parts.items()) + ([("flows.json", json.load(open(flows_path)))] if os.path.exists(flows_path) else [])
    missing = defaultdict(Counter)
    for name, d in docs:
        for e in d.get("edges", []):
            for end in (e["from"], e["to"]):
                if end not in ids:
                    missing[name][end] += 1
        for f in d.get("flows", []):
            for st in f["steps"]:
                if st["node"] not in ids:
                    missing[name]["FLOWSTEP " + st["node"]] += 1
    family = Counter()
    for c in missing.values():
        for k, v in c.items():
            family[k.split(" ")[0] if k.startswith(("ep:", "mcp:", "FLOWSTEP")) else k.split(":")[0] + ":" if ":" in k[:3] else "group"] += v
    print("unresolved by family: " + (", ".join(f"{k} {v}" for k, v in family.most_common()) or "none"))
    for name, c in missing.items():
        items = [(k, v) for k, v in c.most_common() if not a.family or k.startswith(a.family)]
        if items:
            print(f"\n== {name}: {len(items)} distinct")
            for k, v in items[:a.limit]:
                print(f"  {v:3} {k}")


if __name__ == "__main__":
    main()
