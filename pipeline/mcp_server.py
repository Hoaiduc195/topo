"""Topo's maps for coding agents: a Model Context Protocol (MCP) server, read only, standard library only.

usage: python3 -I pipeline/mcp_server.py            (an MCP client starts it and talks over stdin and stdout)

Any MCP client (Claude Code, Codex, Cursor, Gemini CLI and others) can ask a finished map what owns a
file, what a box does, what calls it and what it calls, how a request flows through the system, and
what the analysis found. It never makes or changes a map (the map skill does that) and never runs or
writes anything in a repository.

Maps it serves: every folder holding a topo.config.json in ~/topo-maps/, in Topo's own maps/ (the
example), and in each folder of $TOPO_MAPS (a list separated like PATH, of maps or of folders of maps).
A map without topo-data.json, or with one older than its sources, is built first (build.py, with the
page written to a temporary file, so its dist/ is left as it is).

Every answer gives the commit the map was read at. A box describes the code at that commit, so the
answers say so when a clone on this machine has moved on since, and agents read the cited lines before
relying on a box.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOPO = os.path.dirname(HERE)
VERSION = "0.1.0"
SOURCES = ("topo.config.json", "skeleton.json", "flows.json")

INSTRUCTIONS = """Topo maps are zoomable maps of software systems read from their code: applications, subsystems,
modules and files, down to functions, with the connections between them (calls, requests, reads, writes),
guided flows and an analysis. Every box cites files and lines at the commit the map was read at.

Use topo_owner first when you are working on a file: it says which box owns it and what that part of the
system is. topo_box explains a box and lists its connections; topo_connections follows them further
(what depends on this, what it depends on); topo_find searches by name; topo_flow walks a request through
the system. A box describes the code at the map's commit: when an answer says the clone has moved on,
read the cited lines before relying on it."""


# ---------------------------------------------------------------------------------------------- maps

def map_folders():
    roots = [os.path.expanduser("~/topo-maps"), os.path.join(TOPO, "maps")]
    roots += [os.path.expanduser(p) for p in os.environ.get("TOPO_MAPS", "").split(os.pathsep) if p]
    found = {}
    for r in roots:
        candidates = [r] if os.path.exists(os.path.join(r, "topo.config.json")) else sorted(glob.glob(os.path.join(r, "*")))
        for c in candidates:
            if os.path.exists(os.path.join(c, "topo.config.json")):
                found.setdefault(os.path.realpath(c), None)
    return list(found)


def stale(folder):
    data = os.path.join(folder, "topo-data.json")
    if not os.path.exists(data):
        return True
    newest = max([os.path.getmtime(f) for f in glob.glob(os.path.join(folder, "parts", "*.json"))]
                 + [os.path.getmtime(os.path.join(folder, s)) for s in SOURCES if os.path.exists(os.path.join(folder, s))]
                 or [0])
    return newest > os.path.getmtime(data)


class Map:
    def __init__(self, folder):
        self.folder = folder
        self.name = os.path.basename(folder)
        if stale(folder) and glob.glob(os.path.join(folder, "parts", "*.json")):
            with tempfile.TemporaryDirectory() as t:
                r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "build.py"), folder,
                                    "--out", os.path.join(t, "index.html")], capture_output=True, text=True)
            if r.returncode:
                raise ToolError(f"map {self.name} doesn't build: {(r.stderr or r.stdout).strip()[-400:]}")
        data_path = os.path.join(folder, "topo-data.json")
        if not os.path.exists(data_path):
            raise ToolError(f"map {self.name} has no slices yet (no parts/*.json)")
        self.mtime = os.path.getmtime(data_path)
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
        self.meta = data["meta"]
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.edges = data["edges"]
        self.flows = data.get("flows", [])
        self.children = {}
        for n in data["nodes"]:
            self.children.setdefault(n.get("parent"), []).append(n["id"])
        self.out, self.into = {}, {}
        for e in self.edges:
            self.out.setdefault(e["from"], []).append(e)
            self.into.setdefault(e["to"], []).append(e)
        try:
            with open(os.path.join(folder, "clones.json")) as f:
                self.clones = {k: os.path.expanduser(v) for k, v in json.load(f).items()}
        except (OSError, ValueError):
            self.clones = {}
        self.repos = self.meta.get("repos", [])

    # where a path lives: its repository, its file in that repository, a link and the local clone
    def repo_for(self, path):
        with_prefix = [r for r in self.repos if r.get("prefix") and path.startswith(r["prefix"])]
        if with_prefix:
            return max(with_prefix, key=lambda r: len(r["prefix"]))
        plain = [r for r in self.repos if not r.get("prefix")]
        return plain[0] if len(plain) == 1 else None

    def locate(self, cited):
        m = re.match(r"^(.*?)(?::(\d+)(?:-(\d+))?)?$", cited)
        path, a, b = m.group(1), m.group(2), m.group(3)
        out = {"path": cited}
        repo = self.repo_for(path)
        if not repo:
            return out
        file = path[len(repo.get("prefix") or ""):]
        clone = self.clones.get(repo.get("key"))
        if clone:
            out["local"] = os.path.join(clone, file) + (f":{a}" + (f"-{b}" if b else "") if a else "")
        url, commit = repo.get("url"), repo.get("commit")
        if url and commit:
            host = repo.get("host") or ("bitbucket" if "bitbucket.org" in url else "gitlab" if "//gitlab." in url else "github")
            if host == "bitbucket":
                out["url"] = f"{url}/src/{commit}/{file}" + (f"#lines-{a}" + (f":{b}" if b else "") if a else "")
            else:
                lines = f"#L{a}" + ((("-" if host == "gitlab" else "-L") + b) if b else "") if a else ""
                out["url"] = f"{url}{'/-' if host == 'gitlab' else ''}/blob/{commit}/{file}{lines}"
        return out

    def drift(self):
        """Per repository: the commit the map read, and how far a clone on this machine has moved since."""
        out = []
        for r in self.repos:
            item = {"repository": r.get("name") or r.get("key"), "mapped_at": (r.get("commit") or "")[:12] or None}
            clone = self.clones.get(r.get("key"))
            if clone and r.get("commit") and os.path.isdir(clone):
                try:
                    n = subprocess.run(["git", "-C", clone, "rev-list", "--count", f"{r['commit']}..HEAD"],
                                       capture_output=True, text=True, timeout=10)
                    if n.returncode == 0:
                        item["clone_commits_since"] = int(n.stdout.strip())
                except (OSError, subprocess.TimeoutExpired, ValueError):
                    pass
            out.append(item)
        return out

    def brief(self, nid):
        n = self.nodes.get(nid)
        if not n:
            return {"id": nid}
        out = {"id": nid, "name": n.get("name"), "kind": n.get("kind")}
        if n.get("paths"):
            out["at"] = n["paths"][0]
        return out

    def trail(self, nid):
        names, n = [], self.nodes.get(nid)
        while n and n.get("parent") in self.nodes:
            n = self.nodes[n["parent"]]
            names.append(n.get("name") or n["id"])
        return " > ".join(reversed(names))

    def subtree(self, nid):
        seen, stack = set(), [nid]
        while stack:
            x = stack.pop()
            if x not in seen:
                seen.add(x)
                stack += self.children.get(x, [])
        return seen


class ToolError(Exception):
    pass


CACHE = {}


def here_map(folders):
    """The map whose clone holds the folder the client started this server in, if one does."""
    cwd = os.path.realpath(os.getcwd()) + os.sep
    for f in folders:
        try:
            with open(os.path.join(f, "clones.json")) as fh:
                clones = [os.path.realpath(os.path.expanduser(v)) + os.sep for v in json.load(fh).values()]
        except (OSError, ValueError):
            continue
        if any(cwd.startswith(c) for c in clones):
            return f
    return None


def load(name=None, box=None):
    """The map called name (its folder's name, or a path to it). With no name: the map holding the box
    asked about when only one does, else the map whose clone the client works in, else the only map."""
    folders = map_folders()
    if not name and len(folders) > 1:
        if box:
            having = [f for f in folders if box in load(f).nodes or any(x["id"] == box for x in load(f).flows)]
            if len(having) == 1:
                return load(having[0])
        here = here_map(folders)
        if here:
            return load(here)
    if name:
        path = os.path.realpath(os.path.expanduser(name))
        pick = [f for f in folders if os.path.basename(f) == name or f == path]
        if not pick and os.path.exists(os.path.join(path, "topo.config.json")):
            pick = [path]
        if not pick:
            raise ToolError(f"no map called {name!r}; topo_maps lists them")
        folder = pick[0]
    elif len(folders) == 1:
        folder = folders[0]
    else:
        raise ToolError("several maps: name one (topo_maps lists them)" if folders else
                        "no maps found in ~/topo-maps, Topo's maps/ or $TOPO_MAPS; make one with Topo's map skill")
    m = CACHE.get(folder)
    data = os.path.join(folder, "topo-data.json")
    if not m or stale(folder) or not os.path.exists(data) or os.path.getmtime(data) != m.mtime:
        m = CACHE[folder] = Map(folder)
    return m


# --------------------------------------------------------------------------------------------- tools

def edge_view(m, e, side):
    other = e["to"] if side == "out" else e["from"]
    item = {"kind": e.get("kind"), "label": e.get("label"), side == "out" and "to" or "from": m.brief(other)}
    if e.get("evidence"):
        item["evidence"] = e["evidence"]
    return item


def tool_maps(args):
    out = []
    for f in map_folders():
        try:
            with open(os.path.join(f, "topo.config.json")) as fh:
                cfg = json.load(fh)
        except (OSError, ValueError):
            continue
        item = {"map": os.path.basename(f), "title": cfg.get("title"), "folder": f,
                "repositories": [{k: r.get(k) for k in ("name", "url", "prefix") if r.get(k)}
                                 | {"mapped_at": (r.get("commit") or "")[:12] or None} for r in cfg.get("repos", [])],
                "page": os.path.join(f, "dist", "index.html")}
        try:
            with open(os.path.join(f, "clones.json")) as fh:
                item["clones"] = sorted(os.path.expanduser(v) for v in json.load(fh).values())
        except (OSError, ValueError):
            pass
        out.append(item)
    return {"maps": out}


def score(n, words):
    hay = {"name": (n.get("name") or "").lower(), "id": n["id"].lower(), "summary": (n.get("summary") or "").lower(),
           "paths": " ".join(n.get("paths") or []).lower(), "detail": (n.get("detail") or "").lower()}
    s = 0
    for w in words:
        if w == hay["name"] or hay["id"].endswith("#" + w) or hay["id"].endswith("." + w):
            s += 12
        elif w in hay["name"]:
            s += 6
        elif w in hay["id"]:
            s += 4
        elif w in hay["summary"] or w in hay["paths"]:
            s += 2
        elif w in hay["detail"]:
            s += 1
        else:
            return 0
    return s


def tool_find(args):
    m = load(args.get("map"))
    words = [w for w in re.split(r"\s+", (args.get("query") or "").lower().strip()) if w]
    if not words:
        raise ToolError("query is empty")
    kind = args.get("kind")
    hits = sorted(((score(n, words), n) for n in m.nodes.values() if not kind or n.get("kind") == kind),
                  key=lambda x: -x[0])
    limit = int(args.get("limit") or 15)
    return {"map": m.name, "results": [m.brief(n["id"]) | {"summary": n.get("summary"), "in": m.trail(n["id"])}
                                       for s, n in hits if s > 0][:limit]}


def tool_box(args):
    m = load(args.get("map"), args.get("id"))
    nid = args.get("id") or ""
    n = m.nodes.get(nid)
    if not n:
        close = [x for x in m.nodes if x.endswith(nid) or nid in x][:8]
        raise ToolError(f"no box {nid!r} in {m.name}" + (f"; close: {', '.join(close)}" if close else "; try topo_find"))
    out = {"map": m.name, "id": nid, "in": m.trail(nid)}
    for k in ("name", "kind", "summary", "detail", "signature", "status", "source", "tech", "facts", "code"):
        if n.get(k):
            out[k] = n[k]
    out["paths"] = [m.locate(p) for p in n.get("paths", [])]
    kids = m.children.get(nid, [])
    if kids:
        out["children"] = [m.brief(c) for c in kids[:60]] + ([{"more": len(kids) - 60}] if len(kids) > 60 else [])
    limit = int(args.get("limit") or 25)
    out["calls_out"] = [edge_view(m, e, "out") for e in m.out.get(nid, [])][:limit]
    out["calls_in"] = [edge_view(m, e, "in") for e in m.into.get(nid, [])][:limit]
    flows = [f for f in m.flows if any(s["node"] == nid for s in f.get("steps", []))]
    if flows:
        out["flows"] = [{"id": f["id"], "name": f.get("name")} for f in flows]
    out["mapped_at"] = m.drift()
    return out


def tool_owner(args):
    raw = (args.get("path") or "").strip()
    if not raw:
        raise ToolError("path is empty")
    line = args.get("line")
    m_line = re.match(r"^(.*?):(\d+)$", raw)
    if m_line and line is None:
        raw, line = m_line.group(1), int(m_line.group(2))
    candidates = []   # (map, path as the map cites it)
    maps = [load(args["map"])] if args.get("map") else [load(f) for f in map_folders()]
    absolute = os.path.isabs(os.path.expanduser(raw))
    for m in maps:
        if absolute:
            real = os.path.realpath(os.path.expanduser(raw))
            for r in m.repos:
                clone = m.clones.get(r.get("key"))
                if clone and (real + os.sep).startswith(os.path.realpath(clone) + os.sep):
                    candidates.append((m, (r.get("prefix") or "") + os.path.relpath(real, os.path.realpath(clone))))
        else:
            rel = raw.lstrip("./")
            candidates.append((m, rel))
            for r in m.repos:
                if r.get("prefix") and not rel.startswith(r["prefix"]):
                    candidates.append((m, r["prefix"] + rel))
    results = []
    for m, path in candidates:
        best, spans = [], []
        for n in m.nodes.values():
            for p in n.get("paths", []):
                mm = re.match(r"^(.*?)(?::(\d+)(?:-(\d+))?)?$", p)
                f, a, b = mm.group(1), mm.group(2), mm.group(3)
                if f.endswith("/") and path.startswith(f):
                    best.append((1, len(f), n["id"]))
                elif f == path:
                    if a:
                        spans.append((int(a), int(b) if b else None, n["id"]))
                    else:
                        best.append((3, 0, n["id"]))
        # a box citing only its first line runs until the next box that starts in the file
        starts = sorted({lo for lo, _, _ in spans})
        for lo, hi, nid in spans:
            if hi is None:
                later = [x for x in starts if x > lo]
                hi = later[0] - 1 if later else 10 ** 9
            if line is None:
                best.append((2, 0, nid))
            elif lo <= int(line) <= hi:
                best.append((4, -(hi - lo), nid))
            else:
                best.append((2, -1, nid))
        if not best:
            continue
        best.sort(reverse=True)
        top = best[0]
        owners = [b[2] for b in best if b[:2] == top[:2]]
        file_boxes = sorted({b[2] for b in best if b[0] in (3, 2)})
        nid = owners[0]
        n = m.nodes[nid]
        results.append({"map": m.name, "path": path, "box": m.brief(nid) | {"summary": n.get("summary"), "in": m.trail(nid)},
                        "also": [m.brief(o) for o in owners[1:5]],
                        "symbols_in_file": [m.brief(x) for x in sorted({b[2] for b in best if b[0] == 2})][:30]
                        if line is None or top[0] != 4 else [],
                        "file_boxes": [m.brief(x) for x in file_boxes if x != nid][:5],
                        "mapped_at": m.drift()})
    if not results:
        raise ToolError(f"no box cites {raw}" + (" in a map whose clones hold it" if absolute else "")
                        + "; it may be folded into a parent folder's box, or newer than the map")
    return {"owners": results}


def tool_connections(args):
    m = load(args.get("map"), args.get("id"))
    nid = args.get("id") or ""
    if nid not in m.nodes:
        raise ToolError(f"no box {nid!r} in {m.name}; try topo_find")
    direction = args.get("direction") or "both"
    depth = max(1, min(int(args.get("depth") or 1), 4))
    inside = m.subtree(nid) if args.get("include_children", True) else {nid}
    kinds = set(args.get("kinds") or [])
    limit = int(args.get("limit") or 60)
    out = {"map": m.name, "id": nid, "name": m.nodes[nid].get("name"), "boxes_included": len(inside)}
    for side in (["out", "in"] if direction == "both" else [direction]):
        index = m.out if side == "out" else m.into
        frontier, seen, rows = set(inside), set(inside), []
        for hop in range(1, depth + 1):
            nxt = set()
            for x in frontier:
                for e in index.get(x, []):
                    if kinds and e.get("kind") not in kinds:
                        continue
                    other = e["to"] if side == "out" else e["from"]
                    if other in inside:
                        continue
                    rows.append(edge_view(m, e, side) | {"hop": hop, "via": x if x != nid else None})
                    if other not in seen:
                        seen.add(other)
                        nxt.add(other)
            frontier = nxt
        out["depends_on" if side == "out" else "depended_on_by"] = rows[:limit]
        if len(rows) > limit:
            out[("depends_on" if side == "out" else "depended_on_by") + "_more"] = len(rows) - limit
    out["mapped_at"] = m.drift()
    return out


def tool_flow(args):
    m = load(args.get("map"), args.get("id"))
    fid, query = args.get("id"), (args.get("query") or "").lower()
    if not fid:
        flows = [f for f in m.flows if not query or query in (f.get("name", "") + " " + f.get("summary", "")).lower()]
        flows.sort(key=lambda f: not f.get("featured"))
        return {"map": m.name, "flows": [{"id": f["id"], "name": f.get("name"), "summary": f.get("summary"),
                                          "steps": len(f.get("steps", [])), "featured": bool(f.get("featured"))}
                                         for f in flows]}
    f = next((x for x in m.flows if x["id"] == fid), None)
    if not f:
        raise ToolError(f"no flow {fid!r} in {m.name}; call topo_flow without an id to list them")
    return {"map": m.name, "id": fid, "name": f.get("name"), "summary": f.get("summary"),
            "steps": [{"step": i, "text": s.get("text")} | m.brief(s["node"]) for i, s in enumerate(f.get("steps", []), 1)]}


def tool_analysis(args):
    m = load(args.get("map"))
    path = os.path.join(m.folder, "ANALYSIS.md")
    if not os.path.exists(path):
        raise ToolError(f"{m.name} has no ANALYSIS.md yet (analyze.py writes it)")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    heads = re.findall(r"^## (.+)$", text, re.M)
    section = (args.get("section") or "").lower()
    if not section:
        intro = text.split("\n## ", 1)[0].strip()
        return {"map": m.name, "sections": heads, "intro": intro[:1500]}
    for part in text.split("\n## ")[1:]:
        if part.lower().startswith(section) or section in part.split("\n", 1)[0].lower():
            return {"map": m.name, "section": "## " + part[:12000]}
    raise ToolError(f"no section {section!r}; sections: {', '.join(heads)}")


MAP = {"map": {"type": "string", "description": "The map's name, from topo_maps (optional when there is only one map)"}}
TOOLS = [
    ("topo_maps", tool_maps, "List the Topo maps on this machine: their repositories, the commit each was read at, "
     "the local clones and the page.", {}, []),
    ("topo_owner", tool_owner, "Which box of a map owns a file (and line): what that part of the system is and where "
     "it sits. Give an absolute path in a clone the map knows, or a path as the repository has it.",
     {"path": {"type": "string", "description": "A file path, absolute or relative to its repository; path:line also works"},
      "line": {"type": "integer", "description": "A line in the file, for the box of the symbol around it"}, **MAP}, ["path"]),
    ("topo_box", tool_box, "Everything a map says about one box: what it is, how it works, its files and lines (with "
     "links and local paths), its children, what it calls and what calls it, and the flows it is part of.",
     {"id": {"type": "string", "description": "The box's id, such as f:src/app.py#main"},
      "limit": {"type": "integer", "description": "Connections to list each way (default 25)"}, **MAP}, ["id"]),
    ("topo_connections", tool_connections, "What a box (and everything inside it) depends on and what depends on it, "
     "following connections up to 4 hops: for the impact of a change, or how a part reaches the rest.",
     {"id": {"type": "string"}, "direction": {"type": "string", "enum": ["out", "in", "both"]},
      "depth": {"type": "integer", "description": "Hops to follow, 1 to 4 (default 1)"},
      "kinds": {"type": "array", "items": {"type": "string"},
                "description": "Only these kinds: calls, http, reads, writes, generates, triggers, deploys, configures, tests, documents"},
      "include_children": {"type": "boolean", "description": "Count connections from the boxes inside it too (default true)"},
      "limit": {"type": "integer"}, **MAP}, ["id"]),
    ("topo_find", tool_find, "Search a map's boxes by name, id, summary or path (every word must match somewhere).",
     {"query": {"type": "string"}, "kind": {"type": "string", "description": "Only boxes of this kind (function, class, module, endpoint, ...)"},
      "limit": {"type": "integer"}, **MAP}, ["query"]),
    ("topo_flow", tool_flow, "The guided flows of a map: without an id, list them (featured first, optionally matching a "
     "query); with an id, walk its steps, each on a real box.",
     {"id": {"type": "string"}, "query": {"type": "string"}, **MAP}, []),
    ("topo_analysis", tool_analysis, "The map's analysis (ANALYSIS.md): the strongest coupling, the most depended-on "
     "parts, duplication and unfinished work. Without a section, list the sections.",
     {"section": {"type": "string", "description": "A section heading, or a word from it"}, **MAP}, []),
]


# ------------------------------------------------------------------------------------------ protocol

def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None   # a notification
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion") or "2025-06-18"
        result = {"protocolVersion": version, "capabilities": {"tools": {}},
                  "serverInfo": {"name": "topo", "version": VERSION}, "instructions": INSTRUCTIONS}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "description": d, "annotations": {"readOnlyHint": True},
                             "inputSchema": {"type": "object", "properties": p, "required": r}}
                            for n, _, d, p, r in TOOLS]}
    elif method == "tools/call":
        params = msg.get("params") or {}
        fn = next((f for n, f, *_ in TOOLS if n == params.get("name")), None)
        if not fn:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {params.get('name')}"}}
        try:
            text, err = json.dumps(fn(params.get("arguments") or {}), ensure_ascii=False, indent=1), False
        except ToolError as e:
            text, err = str(e), True
        except Exception as e:  # noqa: BLE001  a tool's failure is reported to the agent, not fatal
            text, err = f"topo: {type(e).__name__}: {e}", True
        result = {"content": [{"type": "text", "text": text}], "isError": err}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = [r for r in map(handle, msg) if r] if isinstance(msg, list) else handle(msg)
        if reply:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
