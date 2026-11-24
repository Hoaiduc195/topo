"""Build the combined, read-only checkout a map is validated against.

usage: python3 -I pipeline/checkout.py MAP_DIR --out DIR [--clones FILE] [--at mapped|head]

A map that holds several repositories cites paths with each repository's folder in front
(repos[].prefix in topo.config.json). This extracts each repository with `git archive` into one
folder: committed files only, so uncommitted work in a clone never reaches the map, and the clone is
not touched. The files are made read-only; the folders are not, so the checkout can be deleted.
--at mapped (the default) uses the commit each repo was mapped at, which is what `validate.py --repo`
checks against; --at head uses each clone's HEAD, for re-mapping.

Where each repository lives on this machine is private, so it is kept outside the config, in
clones.json next to it (or --clones): {"<repos key>": "~/path/to/clone", ...}.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tarfile


def git(clone, *args, binary=False):
    out = subprocess.run(["git", "-C", clone, *args], capture_output=True, check=True).stdout
    return out if binary else out.decode().strip()


def load(map_dir, clones_path=None):
    cfg = json.load(open(os.path.join(map_dir, "topo.config.json")))
    clones_path = clones_path or os.path.join(map_dir, "clones.json")
    if not os.path.exists(clones_path):
        sys.exit(f"checkout: no {clones_path}; write it as {{\"<repos key>\": \"~/path/to/clone\"}}")
    clones = {k: os.path.expanduser(v) for k, v in json.load(open(clones_path)).items()}
    repos = []
    for r in cfg.get("repos", []):
        clone = clones.get(r["key"])
        if not clone:
            print(f"  skip  {r['key']}: no clone listed in clones.json")
            continue
        repos.append((r, clone))
    return cfg, repos


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("map_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--clones")
    ap.add_argument("--at", choices=("mapped", "head"), default="mapped")
    a = ap.parse_args()
    if os.path.exists(a.out) and os.listdir(a.out):
        sys.exit(f"checkout: {a.out} exists and is not empty; pass a new folder")
    _, repos = load(a.map_dir, a.clones)
    # the repository at the root first, so prefixed ones land inside it
    for r, clone in sorted(repos, key=lambda rc: len(rc[0].get("prefix") or "")):
        ref = r.get("commit") if a.at == "mapped" else "HEAD"
        if not ref:
            print(f"  skip  {r['key']}: no mapped commit in the config")
            continue
        dest = os.path.join(a.out, (r.get("prefix") or "").rstrip("/"))
        os.makedirs(dest, exist_ok=True)
        data = git(clone, "archive", ref, binary=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data") if hasattr(tarfile, "data_filter") else tar.extractall(dest)
        print(f"  {r['key']:24} {git(clone, 'rev-parse', '--short', ref)} -> {dest}")
    read_only(a.out)
    print(f"checkout ready: {a.out}")


def read_only(root):
    """Files can't be written, so no agent or tool edits the snapshot a map is checked against.
    Folders stay writable, so the whole checkout can still be deleted with the map."""
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            if not os.path.islink(p):
                os.chmod(p, os.stat(p).st_mode & ~0o222)


if __name__ == "__main__":
    main()
