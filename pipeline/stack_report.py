"""Print a Markdown summary of a map: size, regions, external services and technology.

usage: python3 -I pipeline/stack_report.py MAP_DIR   (run build.py first; reads topo-data.json)
"""
import json
import os
import sys
from collections import Counter, defaultdict


def main(adir):
    d = json.load(open(os.path.join(adir, "topo-data.json")))
    nodes = {n["id"]: n for n in d["nodes"]}

    def root(i):
        while nodes[i].get("parent"):
            i = nodes[i]["parent"]
        return i

    deg = Counter()
    for e in d["edges"]:
        deg[e["from"]] += 1
        deg[e["to"]] += 1
    cross = Counter()
    for e in d["edges"]:
        a, b = root(e["from"]), root(e["to"])
        if a != b:
            cross[tuple(sorted((a, b)))] += 1

    out = [f"## At a glance\n",
           f"- {len(nodes):,} boxes, {len(d['edges']):,} connections, {len(d['flows'])} guided flows "
           f"({sum(1 for f in d['flows'] if f.get('featured'))} featured).",
           f"- {sum(1 for n in nodes.values() if n.get('code'))} boxes carry a verbatim code excerpt; "
           f"{sum(1 for n in nodes.values() if n.get('source') == 'docs')} are known only from documents (dashed outlines)."]
    out.append("\n| Region | Boxes | Mapped from |\n|---|---:|---|")
    for r in [n for n in nodes.values() if not n.get("parent")]:
        size = sum(1 for i in nodes if root(i) == r["id"])
        out.append(f"| {r['name']} | {size:,} | {r.get('provenance', '')} |")
    if cross:
        out.append("\n| Connections between regions | Count |\n|---|---:|")
        for (a, b), c in cross.most_common():
            out.append(f"| {nodes[a]['name']} ↔ {nodes[b]['name']} | {c:,} |")

    groups = defaultdict(list)
    for n in nodes.values():
        if n["kind"] == "external":
            groups[nodes.get(n.get("parent"), {}).get("name", "Other")].append(n)
    out.append("\n## Tooling and services\n\nOutside systems the mapped code depends on, with how many connections reach each.\n")
    out.append("| Service | Group | Connections | What it is used for |\n|---|---|---:|---|")
    rows = [(n, g) for g, ns in groups.items() for n in ns]
    for n, g in sorted(rows, key=lambda x: -deg[x[0]["id"]]):
        out.append(f"| {n['name']} | {g} | {deg[n['id']]} | {n.get('summary', '')} |")

    tech = Counter(t for n in nodes.values() for t in n.get("tech", []) or [])
    out.append("\n## Technology\n\nTags on mapped parts, most used first:\n")
    out.append(", ".join(f"{t} ({c})" for t, c in tech.most_common()))
    print("\n".join(out))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
