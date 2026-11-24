"""What changed in each mapped repository since its mapped commit, and which boxes it touches.

usage: python3 -I pipeline/drift.py MAP_DIR [--clones FILE] [--to REF] [--out drift.json] [--fail-on-drift]

For every repository in topo.config.json with a mapped commit and a clone listed in clones.json
(see checkout.py), it diffs the mapped commit against the clone's HEAD (or --to) and reports:

- cited lines changed: a box cites a line range that a changed hunk touches; re-read it
- file changed: a box's file changed outside the lines it cites; usually still right
- moved / gone: a cited file was renamed (with the new path) or deleted
- uncovered: new files no box cites, by folder: candidates for new boxes
- commits: how many landed since, with the latest subjects (for engagements, new actions to record)

Affected boxes are grouped by the slice (area) that holds them, so only those areas' agents need to
run again. After re-mapping, set each repo's commit in the config to the new head. Read-only.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def git(clone, *args):
    return subprocess.run(["git", "-C", clone, *args], capture_output=True, check=True, text=True).stdout


def changed_lines(clone, base, head, path):
    """Old-side line ranges touched by the diff of one file."""
    out, ranges = git(clone, "diff", "-U0", f"{base}..{head}", "--", path), []
    for line in out.splitlines():
        m = HUNK.match(line)
        if m:
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            ranges.append((start, start + max(count, 1) - 1))
    return ranges


def cited(spec):
    """(file, (lo, hi) or None) from 'path:120-168', 'path:120' or 'path'."""
    m = re.match(r"^(.*?)(?::(\d+)(?:-(\d+))?)?$", spec)
    lo = int(m.group(2)) if m.group(2) else None
    return m.group(1), ((lo, int(m.group(3) or lo)) if lo else None)


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("map_dir")
    ap.add_argument("--clones")
    ap.add_argument("--to", default="HEAD")
    ap.add_argument("--out")
    ap.add_argument("--fail-on-drift", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(a.map_dir, "topo.config.json")))
    clones_path = a.clones or os.path.join(a.map_dir, "clones.json")
    if not os.path.exists(clones_path):
        sys.exit(f"drift: no {clones_path}; write it as {{\"<repos key>\": \"~/path/to/clone\"}}")
    clones = {k: os.path.expanduser(v) for k, v in json.load(open(clones_path)).items()}

    # every cited path, with the slice that cites it
    cites = defaultdict(list)
    for part in sorted(glob.glob(os.path.join(a.map_dir, "parts", "*.json"))):
        area = json.load(open(part)).get("area", os.path.basename(part))
        for n in json.load(open(part))["nodes"]:
            for spec in n.get("paths") or []:
                f, rng = cited(spec)
                cites[f].append((n["id"], area, rng))

    report, drifted = {"repos": []}, False
    for r in cfg.get("repos", []):
        clone, base = clones.get(r["key"]), r.get("commit")
        if not clone or not base:
            continue
        prefix = r.get("prefix") or ""
        try:
            head = git(clone, "rev-parse", a.to).strip()
            log = git(clone, "log", "--format=%h %cs %s", f"{base}..{head}").splitlines()
            status = git(clone, "diff", "--name-status", "-M", f"{base}..{head}").splitlines()
        except subprocess.CalledProcessError as exc:
            print(f"✗ {r['key']}: {exc.stderr.strip()[:200]}")
            continue
        rep = {"key": r["key"], "name": r.get("name"), "mapped": base[:9], "head": head[:9], "commits": len(log),
               "latest": log[:8], "areas": defaultdict(list), "uncovered": defaultdict(int)}
        for line in status:
            parts = line.split("\t")
            kind, old, new = parts[0][0], parts[1], parts[-1]
            o, n_ = prefix + old, prefix + new
            if kind == "A":
                if n_ not in cites:
                    folder = os.path.dirname(new) or "."
                    rep["uncovered"][folder] += 1
                continue
            for node, area, rng in cites.get(o, []):
                if kind == "D":
                    rep["areas"][area].append({"id": node, "reason": "gone", "path": o})
                elif kind == "R":
                    rep["areas"][area].append({"id": node, "reason": "moved", "path": o, "to": n_})
                elif rng is None:
                    rep["areas"][area].append({"id": node, "reason": "file changed", "path": o})
                else:
                    hit = any(lo <= rng[1] and hi >= rng[0] for lo, hi in changed_lines(clone, base, head, old))
                    rep["areas"][area].append({"id": node, "reason": "cited lines changed" if hit else "file changed",
                                               "path": o})
        drifted |= bool(log)
        report["repos"].append(rep)
        affected = sum(len(v) for v in rep["areas"].values())
        print(f"\n== {r.get('name') or r['key']}: mapped {rep['mapped']}, now {rep['head']}, {len(log)} commit(s) since")
        if not log:
            continue
        for line in log[:5]:
            print(f"   {line[:110]}")
        reasons = defaultdict(int)
        for items in rep["areas"].values():
            for it in items:
                reasons[it["reason"]] += 1
        print(f"   boxes touched: {affected} ({', '.join(f'{k} {v}' for k, v in sorted(reasons.items())) or 'none'})")
        for area, items in sorted(rep["areas"].items(), key=lambda kv: -len(kv[1])):
            strong = sum(1 for it in items if it["reason"] != "file changed")
            print(f"   area {area}: {len(items)} box(es), {strong} needing a re-read")
        if rep["uncovered"]:
            top = sorted(rep["uncovered"].items(), key=lambda kv: -kv[1])[:6]
            print("   new files no box cites: " + ", ".join(f"{d} ({c})" for d, c in top))
    if a.out:
        json.dump(report, open(a.out, "w"), indent=1, default=dict)
        print(f"\nworklist: {a.out}")
    if not drifted:
        print("\nno drift: every mapped repository is at its mapped commit")
    sys.exit(1 if drifted and a.fail_on_drift else 0)


if __name__ == "__main__":
    main()
