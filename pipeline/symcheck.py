"""Check that every symbol box cites a line where that symbol actually appears.

usage: python3 -I pipeline/symcheck.py MAP_DIR --repo CHECKOUT   (run build.py first)

For each `f:<path>#<Symbol>` node whose first path carries a line number, the last part of the
symbol name must appear within three lines of the cited line. Mismatches usually mean a mapping
agent cited the wrong line; Markdown section ids (e.g. #SectionA vs "Section A") are the common
false alarm.
"""
import argparse
import json
import os
import re

ap = argparse.ArgumentParser()
ap.add_argument("map_dir")
ap.add_argument("--repo", required=True)
a = ap.parse_args()
d = json.load(open(os.path.join(a.map_dir, "topo-data.json")))
cache, ok, bad, skipped = {}, 0, [], 0
for n in d["nodes"]:
    if not n["id"].startswith("f:") or "#" not in n["id"] or not n.get("paths"):
        continue
    m = re.match(r"^(.*?):(\d+)(?:-\d+)?$", n["paths"][0])
    key = re.sub(r"[^A-Za-z0-9_\-]", "", re.split(r"[.\s/]", n["id"].split("#", 1)[1])[-1])
    if not m or len(key) < 3:
        skipped += 1
        continue
    path, line = m.group(1), int(m.group(2))
    if path not in cache:
        try:
            cache[path] = open(os.path.join(a.repo, path), errors="replace").read().split("\n")
        except OSError:
            cache[path] = None
    lines = cache[path]
    if lines is None:
        skipped += 1
    elif key.lower() in "\n".join(lines[max(0, line - 4): line + 3]).lower():
        ok += 1
    else:
        bad.append(f"{n['id']} @ {n['paths'][0]}")
print(f"symbol/line agreement: {ok} ok, {len(bad)} mismatched, {skipped} not checkable")
for b in bad[:50]:
    print("  ", b)
