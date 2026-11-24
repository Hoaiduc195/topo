"""Validate map slice files against pipeline/SCHEMA.md.

usage:
  python3 -I pipeline/validate.py MAP_DIR [--repo CODEBASE_ROOT] [PART.json ...]

With no part files, every MAP_DIR/parts/*.json is checked. With --repo, every cited
path (and line number) must exist in that checkout, which is how mapping agents prove
their claims; without it, path checks are skipped (e.g. for an anonymized map).
Prints every error and warning; ends with OK when there are no errors.
"""
import json
import os
import re
import sys

REPO = None          # set from --repo; None skips filesystem checks
SKELETON = None      # MAP_DIR/skeleton.json

NODE_KINDS = {"group", "service", "module", "component", "function", "class", "endpoint",
              "data", "config", "doc", "agent", "workflow", "job", "test", "external", "app"}
EDGE_KINDS = {"calls", "http", "reads", "writes", "generates", "triggers", "deploys",
              "configures", "tests", "documents"}
STATUSES = {"live", "built", "partial", "stub", "planned", "archived", "unknown"}
SOURCES = {"code", "docs", "inferred"}
EP_SERVICES = set()  # from topo.config.json: endpoint_services, or the endpoint_fallback keys
PHASES = set()       # from topo.config.json: process step ids, for a node's "phase"
CFG = {}             # topo.config.json
CAPS = set()         # from topo.config.json: the capability vocabulary, for a node's "capabilities"
DATE_RX = re.compile(r"\d{4}-\d{2}(-\d{2})?$")
SECRET_RX = re.compile(r"(sk-ant-[A-Za-z0-9]|sk-[A-Za-z0-9]{20}|xox[bp]-[0-9A-Za-z]|ghp_[A-Za-z0-9]{10}|"
                       r"github_pat_|AKIA[0-9A-Z]{12}|-----BEGIN [A-Z ]*PRIVATE KEY|ntn_[A-Za-z0-9]{10}|"
                       r"secret_[A-Za-z0-9]{20})")

errors, warnings = [], []
_line_cache = {}


def err(where, msg):
    errors.append(f"ERROR  {where}: {msg}")


def warn(where, msg):
    warnings.append(f"warn   {where}: {msg}")


def n_lines(rel):
    if rel not in _line_cache:
        try:
            with open(os.path.join(REPO, rel), "rb") as fh:
                _line_cache[rel] = fh.read().count(b"\n") + 1
        except OSError:
            _line_cache[rel] = None
    return _line_cache[rel]


def check_path(where, spec):
    """spec = 'path', 'path:12' or 'path:12-40'; directories may end with '/'."""
    if not isinstance(spec, str) or not spec:
        err(where, f"bad path entry {spec!r}")
        return
    m = re.match(r"^(.*?)(?::(\d+)(?:-(\d+))?)?$", spec)
    rel, a, b = m.group(1), m.group(2), m.group(3)
    if rel.startswith("/") or rel.startswith("./"):
        err(where, f"path must be repo-relative without leading / or ./ : {spec!r}")
        return
    if REPO is None:
        return
    full = os.path.join(REPO, rel)
    if not os.path.exists(full):
        err(where, f"path does not exist in repo: {rel!r}")
        return
    if a:
        if os.path.isdir(full):
            err(where, f"line number on a directory: {spec!r}")
            return
        total = n_lines(rel)
        hi = int(b or a)
        if total is not None and hi > total:
            err(where, f"line {hi} beyond end of {rel} ({total} lines)")
        if b and int(b) < int(a):
            err(where, f"reversed range {spec!r}")


def path_of_ref(rid):
    if rid.startswith("f:"):
        return rid[2:].split("#", 1)[0]
    if rid.startswith("d:"):
        return rid[2:]
    return None


def check_ref_form(where, rid, known):
    """An edge/flow endpoint: a known node, or a resolvable cross-area reference."""
    if rid in known:
        return
    if rid.startswith(("f:", "d:")):
        p = path_of_ref(rid)
        if REPO is not None and not os.path.exists(os.path.join(REPO, p)):
            err(where, f"reference to non-existent path {rid!r}")
        return
    if rid.startswith("ep:"):
        m = re.match(r"^ep:(\S+) (GET|POST|PUT|PATCH|DELETE) (/\S*)$", rid)
        if not m or (EP_SERVICES and m.group(1) not in EP_SERVICES):
            err(where, f"bad endpoint id {rid!r} (form 'ep:<service> <METHOD> <path>', service in {sorted(EP_SERVICES)})")
        return
    if rid.startswith("mcp:") or rid.split("/")[0].endswith(":agent") or rid.startswith(PREFIX_REFS):
        return
    err(where, f"unknown node id {rid!r} (not in your files or the skeleton, and not a resolvable f:/d:/ep:/mcp:/<app>:agent/ reference)")


def text_checks(where, s):
    if SECRET_RX.search(s):
        err(where, "looks like it contains a secret/token; remove it")
    if "\u2014" in s:
        warn(where, "contains an em dash (team style forbids them)")


def check_abbrev(where, nd):
    ab = nd.get("abbrev")
    if ab is not None and not (isinstance(ab, str) and 1 <= len(ab) <= 3 and ab.strip() == ab):
        err(where, "abbrev must be 1 to 3 characters with no spaces around them (the badge on the box's card)")


def check_decisions(known):
    """topo.config.json decisions: what the Boundaries rail lists. Each has a title, and may name a box."""
    ds = CFG.get("decisions")
    if ds is None:
        return
    if not isinstance(ds, list):
        err("topo.config.json decisions", "must be a list of {title, detail?, node?, status?}")
        return
    for i, d in enumerate(ds):
        where = f"topo.config.json decisions[{i}]"
        if not isinstance(d, dict) or not isinstance(d.get("title"), str) or not d["title"].strip():
            err(where, "needs a title")
            continue
        for f in ("detail", "status", "node"):
            if f in d and not isinstance(d[f], str):
                err(where, f"{f} must be text")
        extra = set(d) - {"title", "detail", "node", "status"}
        if extra:
            err(where, f"unknown field(s) {sorted(extra)}")
        if isinstance(d.get("node"), str):
            check_ref_form(where + ".node", d["node"], known)
        for f in ("title", "detail"):
            if isinstance(d.get(f), str):
                text_checks(where + f".{f}", d[f])


def main(paths):
    skel = json.load(open(SKELETON))
    skel_ids = {n["id"] for n in skel["nodes"]}
    parts = []
    for p in paths:
        try:
            parts.append((p, json.load(open(p))))
        except Exception as e:  # noqa: BLE001
            err(p, f"invalid JSON: {e}")
    if errors:
        return

    nodes, ids = [], set()
    for p, doc in parts:
        for key in ("area", "nodes", "edges"):
            if key not in doc:
                err(p, f"missing top-level key {key!r}")
        for i, nd in enumerate(doc.get("nodes", [])):
            where = f"{os.path.basename(p)} node[{i}] {nd.get('id', '?')}"
            for f in ("id", "parent", "name", "kind", "summary"):
                if f not in nd:
                    err(where, f"missing field {f!r}")
            nid = nd.get("id")
            if not isinstance(nid, str):
                continue
            if nid in ids or nid in skel_ids:
                err(where, "duplicate id (already defined here or in the skeleton)")
            ids.add(nid)
            nodes.append((where, nd))

    known = ids | skel_ids
    by_id = {nd["id"]: nd for _, nd in nodes}
    for n in skel["nodes"]:
        by_id.setdefault(n["id"], n)
        check_abbrev(f"skeleton.json {n['id']}", n)
    check_decisions(known)

    for where, nd in nodes:
        nid = nd["id"]
        if nid.startswith("x:"):
            err(where, "x: ids are reserved for the skeleton's external systems")
        if nid.startswith(("f:", "d:")):
            p = path_of_ref(nid)
            if REPO is not None and not os.path.exists(os.path.join(REPO, p)):
                err(where, f"id path does not exist: {p!r}")
        elif nid.startswith(("ep:", "mcp:")) or nid.split("/")[0].endswith(":agent") or nid.startswith(PREFIX_REFS):
            check_ref_form(where, nid, set())
        elif not re.match(r"^[a-z][a-z0-9-]*(\.[a-z0-9][a-z0-9_-]*)+$", nid):
            err(where, "group ids must look like '<prefix>.<slug>[.<slug>]' (lowercase)")
        par = nd.get("parent")
        if par is None:
            err(where, "parent must not be null (top-level nodes are predefined)")
        elif par not in known:
            err(where, f"parent {par!r} not found in your files or the skeleton")
        elif par == nid:
            err(where, "node is its own parent")
        if nd.get("kind") not in NODE_KINDS:
            err(where, f"kind {nd.get('kind')!r} not in {sorted(NODE_KINDS)}")
        if nd.get("kind") == "app":
            err(where, "kind 'app' is reserved for the skeleton")
        name = nd.get("name", "")
        if len(name) > 48:
            warn(where, f"name longer than 48 chars ({len(name)})")
        s = nd.get("summary", "")
        if not s or len(s) > 200:
            err(where, f"summary must be 1..200 chars (is {len(s)})")
        d = nd.get("detail")
        if d is not None and len(d) > 1200:
            err(where, f"detail longer than 1200 chars ({len(d)})")
        if nd.get("kind") in ("group", "service", "module") and not d:
            warn(where, "groups/services/modules should have a 'detail' explaining how it works")
        if "status" in nd and nd["status"] not in STATUSES:
            err(where, f"status {nd['status']!r} not in {sorted(STATUSES)}")
        if "source" in nd and nd["source"] not in SOURCES:
            err(where, f"source {nd['source']!r} not in {sorted(SOURCES)}")
        for spec in nd.get("paths", []) or []:
            check_path(where, spec)
        if nid.startswith("f:") and not nd.get("paths"):
            warn(where, "file/symbol node without 'paths' (add the file, with a line for symbols)")
        facts = nd.get("facts", []) or []
        if not isinstance(facts, list) or len(facts) > 5:
            err(where, "facts must be a list of at most 5 strings")
        if "phase" in nd and nd["phase"] not in PHASES:
            err(where, f"phase {nd['phase']!r} is not a process step in topo.config.json")
        if "date" in nd and not DATE_RX.match(str(nd["date"])):
            err(where, "date must look like 2026-08-15 or 2026-08")
        check_abbrev(where, nd)
        caps = nd.get("capabilities", [])
        if not isinstance(caps, list):
            err(where, "capabilities must be a list of tags")
        else:
            for c in caps:
                if c not in CAPS:
                    warn(where, f"capability {c!r} is not in the map's vocabulary (topo.config.json capabilities)")
        code = nd.get("code")
        if code is not None and code.count("\n") + 1 > 15:
            err(where, "code excerpt longer than 15 lines")
        for f in ("name", "summary", "detail", "signature", "code"):
            if isinstance(nd.get(f), str):
                text_checks(where + f".{f}", nd[f])
        for f in facts:
            if isinstance(f, str):
                text_checks(where + ".facts", f)

    # parent cycles
    for where, nd in nodes:
        seen, cur = set(), nd["id"]
        while cur is not None and cur in by_id:
            if cur in seen:
                err(where, "parent chain has a cycle")
                break
            seen.add(cur)
            cur = by_id[cur].get("parent")

    n_edges = 0
    for p, doc in parts:
        for i, e in enumerate(doc.get("edges", [])):
            n_edges += 1
            where = f"{os.path.basename(p)} edge[{i}] {e.get('from')} -> {e.get('to')}"
            for f in ("from", "to", "kind", "label", "evidence"):
                if f not in e:
                    err(where, f"missing field {f!r}")
            for end in ("from", "to"):
                if isinstance(e.get(end), str):
                    check_ref_form(where, e[end], known)
            if e.get("from") == e.get("to"):
                err(where, "self-loop")
            if e.get("kind") not in EDGE_KINDS:
                err(where, f"kind {e.get('kind')!r} not in {sorted(EDGE_KINDS)}")
            if "status" in e and e["status"] != "idea":
                err(where, f"status {e['status']!r}: an edge's only status is 'idea'")
            if "url" in e and not str(e["url"]).startswith("https://"):
                err(where, "url must start with https://")
            if len(e.get("label", "")) > 60:
                warn(where, "label longer than 60 chars")
            if isinstance(e.get("evidence"), str):
                check_path(where + " evidence", e["evidence"])
            for f in ("label", "detail"):
                if isinstance(e.get(f), str):
                    text_checks(where + f".{f}", e[f])
        for i, fl in enumerate(doc.get("flows", []) or []):
            where = f"{os.path.basename(p)} flow[{i}] {fl.get('id')}"
            for f in ("id", "name", "steps"):
                if f not in fl:
                    err(where, f"missing field {f!r}")
            for j, st in enumerate(fl.get("steps", [])):
                if "node" not in st or "text" not in st:
                    err(where, f"step {j} needs 'node' and 'text'")
                else:
                    check_ref_form(f"{where} step {j}", st["node"], known)

    print(f"{len(nodes)} nodes, {n_edges} edges checked")


PREFIX_REFS = ()

if __name__ == "__main__":
    import argparse
    import glob
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("map_dir")
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--repo")
    a = ap.parse_intermixed_args()  # part files may come before or after --repo
    REPO = os.path.abspath(a.repo) if a.repo else None
    SKELETON = os.path.join(a.map_dir, "skeleton.json")
    cfg_path = os.path.join(a.map_dir, "topo.config.json")
    cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}
    CFG = cfg
    EP_SERVICES = set(cfg.get("endpoint_services") or cfg.get("endpoint_fallback", {}).keys())
    PREFIX_REFS = tuple(cfg.get("prefix_fallback", {}).keys())
    PHASES = {p["id"] for p in cfg.get("process", [])}
    CAPS = set(cfg.get("capabilities", {}))
    files = a.parts or sorted(glob.glob(os.path.join(a.map_dir, "parts", "*.json")))
    main(files)
    for w in warnings:
        print(w)
    for e in errors:
        print(e)
    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s). Fix the errors and re-run.")
        sys.exit(1)
    print(f"\nOK ({len(warnings)} warning(s))")
