"""Check the contracts between systems: every route a caller uses must be one its target serves.

usage: python3 -I pipeline/contracts.py CONTRACTS.json [--out report.json] [--mirrors PRIVATE]

A contract names a target, a repository at a commit whose served routes come from routes.py (or
from an OpenAPI JSON file), and its callers: repositories, and how to find their calls to the
target. A call is a string that starts with the target's base URL:

- an f-string or template literal that interpolates a base name: f"{ORDERS_API_URL}/v1/orders",
  `${this.baseUrl}/v1/orders`
- a concatenation, BASE + "/v1/orders", or urljoin(BASE, "/v1/orders")
- a request on a client built with that base: client.post("/v1/orders")
- a shell variable: curl -X POST "$BASE/v1/orders" or "${BASE}/v1/orders"
- a literal URL that matches one of the caller's patterns: "https://api.example.com/v1/orders"

A name assigned from a base name is followed as a base too, from that line until it is assigned
something else, so `url = os.getenv("ORDERS_API_URL")`, `self.endpoint = ...` and
`async with httpx.AsyncClient(base_url=BASE) as client` are all found. Each call's method is read
from the request around it when it is plain (`.post(`, `"POST",`, `method: "POST"`, curl's `-X`),
else any method the target serves for that path counts.

It reports every route a caller uses that the target does not serve, or serves only with other
methods. A caller that pins the target, as a git submodule or a vendored copy, is also checked
against the routes at the pinned commit, and the report says how many commits the pin is behind
the target's commit.

Exit code 1 when any check fails, 2 when the contracts file or a repository is wrong. A failure
already reported to its owner can be listed in the caller's `known`: it is still printed, marked
known, but does not fail the run (--strict fails on it too). A known failure that no longer
fails does, so the list only shrinks.

Read-only: every repository is read from `git archive` of a commit into a temporary folder, never
from its working tree, and nothing is written to it. Contracts that name a client's repository
live in your private folder (pipeline/settings.py), never in this repository.

--mirrors reads each repository from the drift watch's mirror of it instead, where it has one: a
map's clones.json names the working clone, and the watch's mirrors/<map>.clones.json the mirror,
under the same key. The machine that runs the checks needs no clones then, and every check reads
the upstream heads of the watch's last fetch.

The contracts file:

  {"contracts": [{
     "name": "Platform API",
     "target": {"repo": "~/src/platform", "commit": "HEAD", "folder": "api"},
     "callers": [{"name": "Shop", "repo": "~/src/shop", "bases": ["PLATFORM_URL"],
                  "patterns": ["https://api\\\\.platform\\\\.example"],
                  "pin": {"path": "vendor/platform"}}]}]}

- target: `repo` (a clone or a mirror), `commit` (default HEAD), and either `folder` (default the
  root; routes.py reads it) or `openapi` (a JSON file: a path in the repository at that commit, or
  an absolute path on this machine). `base_path` is put in front of every served route.
- callers[]: `name`, `repo`, `commit`, `folder` (where to look for calls, default the root),
  `bases` (names that hold the target's base URL), `patterns` (regular expressions for literal
  base URLs), `strip` (a path prefix the caller's base URL carries, removed before matching),
  `tests` (true to read test files too) and `pin`.
- pin: `path` of the submodule or vendored copy in the caller. A submodule's commit comes from the
  caller's tree; a vendored copy's from `commit` here, else a `commit <sha>` line in its VENDORED
  file. `folder` (default the target's) is where its routes are. `max_behind` fails the check
  when the pin is further behind than that many commits.
- known: failures already routed, as "METHOD /path" (as the report prints it) or
  {"route": "METHOD /path", "why": "where it was reported"}.
"""
import argparse
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile

# loaded by path: python3 -I keeps the script's folder off sys.path
_spec = importlib.util.spec_from_file_location("routes", os.path.join(os.path.dirname(os.path.abspath(__file__)), "routes.py"))
routes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(routes)

CODE = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash")
NAME = r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*"
# a URL path inside a string: plain characters and {param} / ${param} placeholders; a placeholder may
# quote (f"/items/{quote(key, safe='')}"), since its quotes cannot end the string around it
PATH = r"(?P<path>/(?:[^\"'`\s{}$\\]|\$?\{[^{}\n]*\})*)"
SITES = [
    ("interpolation", re.compile(r"\$?\{\s*(?P<name>" + NAME + r")(?:\.(?:rstrip|replace|strip)\([^)]*\))?\s*\}" + PATH)),
    ("concatenation", re.compile(r"(?P<name>" + NAME + r")\s*\+\s*[rfb]?[\"'`]" + PATH)),
    ("urljoin", re.compile(r"urljoin\(\s*(?P<name>" + NAME + r")\s*,\s*[rf]?[\"']" + PATH)),
    ("client", re.compile(r"(?P<name>" + NAME + r")\.(?P<method>get|post|put|patch|delete)\(\s*[rf]?[\"'`]" + PATH)),
    ("shell", re.compile(r"\$(?P<name>[A-Za-z_]\w*)" + PATH)),
]
ASSIGN = re.compile(r"^[ \t]*(?:(?:export|const|let|var|private|public|protected|readonly|static)\s+)*(?P<name>" + NAME +
                    r")[ \t]*(?::[^=\n]+?)?[ \t]*=(?![=>])", re.M)
WITH_AS = re.compile(r"\bwith\s+(?P<expr>[^\n]+?)\s+as\s+(?P<name>\w+)\s*:")
METHOD_BEFORE = [
    re.compile(r"\.(get|post|put|patch|delete)\s*\(\s*(?:url\s*=\s*)?[frb]*$", re.I),
    re.compile(r"[\"'](get|post|put|patch|delete)[\"']\s*,\s*(?:url\s*=\s*)?[frb]*$", re.I),
    re.compile(r"method\s*=\s*[\"'](get|post|put|patch|delete)[\"']\s*,\s*(?:url\s*=\s*)?[frb]*$", re.I),
]
FETCH_BEFORE = re.compile(r"\bfetch\s*\(\s*$")
FETCH_METHOD = re.compile(r"method\s*[:=]\s*[\"'](get|post|put|patch|delete)[\"']", re.I)
CURL_METHOD = re.compile(r"(?:-X|--request)\s*[\"']?(get|post|put|patch|delete)\b", re.I)
CURL_DATA = re.compile(r"\s(?:-d|--data(?:-raw|-binary|-urlencode)?|-F|--form|--json)\b")
URL_VAR_BEFORE = re.compile(r"(?P<var>" + NAME + r")\s*(?::[^=\n]+?)?=\s*[frb]*$")


class ContractError(Exception):
    pass


def git(repo, *args, binary=False):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if r.returncode:
        raise ContractError(f"git {' '.join(args[:3])} in {repo}: {r.stderr.decode(errors='replace').strip()[:200]}")
    return r.stdout if binary else r.stdout.decode(errors="replace").strip()


def snapshot(repo, commit, dest, folder=""):
    """Extract `folder` of `repo` at `commit` into `dest`: committed files only, the repository untouched."""
    args = ["archive", commit] + (["--", folder] if folder.strip("/.") else [])
    data = git(repo, *args, binary=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data") if hasattr(tarfile, "data_filter") else tar.extractall(dest)


# ---- paths

def segments(path):
    """'/learnings/{id}/feedback?x=1' -> ['learnings', '*', 'feedback']; a {name:path} converter -> '**'."""
    path = re.split(r"[?#]", path, maxsplit=1)[0]
    out = []
    for s in (s for s in path.strip("/").split("/") if s):
        if re.fullmatch(r"\{[^{}]*:path\}|\*\w*", s):
            out.append("**")
        elif "{" in s or "$" in s or "<" in s or s.startswith(":"):
            out.append("*")
        else:
            out.append(s)
    return out


def path_matches(route, call):
    if route and route[-1] == "**":
        head = route[:-1]
        return len(call) > len(head) and all(r == "*" or c == "*" or r == c for r, c in zip(head, call))
    return len(route) == len(call) and all(r == "*" or c == "*" or r == c for r, c in zip(route, call))


class Served:
    """A target's routes at one commit."""

    def __init__(self, rows, label):
        self.rows = [(m.upper(), p, loc, segments(p)) for m, p, loc in rows]
        self.label = label

    def check(self, method, path):
        """('served', [rows]) | ('method', [rows with the path under other methods]) | ('missing', [hints])."""
        segs = segments(path)
        hits = [r for r in self.rows if path_matches(r[3], segs)]
        if hits and (method is None or any(r[0] == method for r in hits)):
            return "served", [r for r in hits if method is None or r[0] == method]
        if hits:
            return "method", hits
        first = segs[0] if segs else ""
        return "missing", [r for r in self.rows if r[3][:1] == [first]][:4]


def target_routes(target, commit, cache, folder=None, label=None):
    """Served routes of the target at `commit` (a full sha), from routes.py or an OpenAPI file."""
    folder = target.get("folder", "") if folder is None else folder
    key = (target["repo"], commit, folder, target.get("openapi"))
    if key in cache:
        return cache[key]
    repo = os.path.expanduser(target["repo"])
    if target.get("openapi"):
        spec_path = os.path.expanduser(target["openapi"])
        if os.path.isabs(spec_path):
            text = open(spec_path, encoding="utf-8").read()
            where = spec_path
        else:
            text = git(repo, "show", f"{commit}:{target['openapi']}")
            where = target["openapi"]
        spec = json.loads(text)
        rows = [(m.upper(), p, where) for p, ops in (spec.get("paths") or {}).items() for m in ops
                if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")]
    else:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot(repo, commit, tmp, folder)
            rows = routes.collect(tmp, folder or ".")
    base = (target.get("base_path") or "").rstrip("/")
    served = Served([(m, base + p, loc) for m, p, loc in rows], label or commit[:9])
    cache[key] = served
    return served


# ---- calls

def statement_end(text, i):
    """End of the expression that starts at i: the first newline (or ;) outside brackets."""
    depth, n = 0, min(len(text), i + 2000)
    while i < n:
        c = text[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth < 0:
                return i
        elif (c == "\n" or c == ";") and depth <= 0:
            return i
        i += 1
    return i


def mentions(expr, names, bases, patterns):
    """Does `expr` use a base? A base constant counts as an attribute too (config.BASE_URL)."""
    return any(re.search((r"(?<![\w$])" if n in bases else r"(?<![\w$.])") + re.escape(n) + r"(?![\w$])", expr)
               for n in names) or any(p.search(expr) for p in patterns)


def is_comment(text, pos):
    line = text[text.rfind("\n", 0, pos) + 1:pos].lstrip()
    return line.startswith(("#", "//", "*", "/*"))


def literal_start(text, pos):
    """Index of the quote that opens the string literal holding `pos`, on the same line."""
    line_start = text.rfind("\n", 0, pos) + 1
    seg = text[line_start:pos]
    q = max(seg.rfind('"'), seg.rfind("'"), seg.rfind("`"))
    return line_start + q if q >= 0 else pos


def curl_method(text, start, end):
    """The method of a curl command around a URL: -X / --request, else POST with data, else GET."""
    before = text[max(0, start - 300):start]
    k = before.rfind("curl ")
    if k < 0:
        return None
    head = before[k:].split("\n")
    if not all(line.rstrip().endswith("\\") for line in head[:-1]):
        return None  # that curl is an earlier command
    rest = text[end:end + 2000].split("\n")
    tail, i = rest[0], 0
    while rest[i].rstrip().endswith("\\") and i + 1 < len(rest):
        i += 1
        tail += "\n" + rest[i]
    cmd = before[k:] + tail
    m = CURL_METHOD.search(cmd)
    return m.group(1).upper() if m else "POST" if CURL_DATA.search(cmd) else "GET"


def infer_method(text, start, end):
    """The HTTP method of the request a URL string at text[start:end] is passed to, or None."""
    curl = curl_method(text, start, end)
    if curl:
        return curl
    before = text[max(0, start - 200):start]
    for rx in METHOD_BEFORE:
        m = rx.search(before)
        if m:
            return m.group(1).upper()
    if FETCH_BEFORE.search(before.rstrip("frb")):
        m = FETCH_METHOD.search(text[end:end + 400])
        return m.group(1).upper() if m else "GET"
    m = URL_VAR_BEFORE.search(before)
    if m:  # url = f"{BASE}/x" ... client.post(url): follow the variable to its request
        var = re.escape(m.group("var"))
        after = text[end:end + 4000]
        for rx in (r"\.(get|post|put|patch|delete)\s*\(\s*(?:url\s*=\s*)?" + var + r"\b",
                   r"[\"'](get|post|put|patch|delete)[\"']\s*,\s*(?:url\s*=\s*)?" + var + r"\b"):
            found = re.search(rx, after, re.I)
            if found:
                return found.group(1).upper()
        found = re.search(r"\bfetch\s*\(\s*" + var + r"\b", after)
        if found:
            fm = FETCH_METHOD.search(after[found.end():found.end() + 400])
            return fm.group(1).upper() if fm else "GET"
    return None


def find_calls(text, bases, patterns):
    """[(method or None, path, line, how)] for every call to the target's base URL in one file."""
    events = []
    for m in ASSIGN.finditer(text):
        events.append((m.end(), "assign", m.group("name"), text[m.end():statement_end(text, m.end())]))
    for m in WITH_AS.finditer(text):
        events.append((m.start(), "assign", m.group("name"), m.group("expr")))
    for how, rx in SITES:
        for m in rx.finditer(text):
            events.append((m.start(), "site", how, m))
    for p in patterns:
        for m in re.finditer(r"[\"'`](?:" + p.pattern + r")" + PATH, text):
            events.append((m.start(), "site", "literal", m))
    events.sort(key=lambda e: (e[0], e[1] == "site"))
    active, calls = set(bases), []
    for pos, kind, a, b in events:
        if kind == "assign":
            name, expr = a, b
            full_url = any(rx.search(expr) for _, rx in SITES) or \
                any(re.search(r"[\"'`](?:" + p.pattern + r")/", expr) for p in patterns)
            if not full_url and mentions(expr, active, bases, patterns):
                active.add(name)
            elif name not in bases:  # assigned a full URL or something else: no longer a base
                active.discard(name)
            continue
        how, m = a, b
        if how != "literal" and m.group("name") not in active and m.group("name").split(".")[-1] not in bases:
            continue
        if is_comment(text, pos):
            continue
        method = m.group("method").upper() if how == "client" else \
            infer_method(text, literal_start(text, m.start("path")), m.end())
        path = re.split(r"[?#]", m.group("path"), maxsplit=1)[0].rstrip("/") or "/"
        calls.append((method, path, text.count("\n", 0, pos) + 1, how))
    return calls


def caller_calls(caller, commit, skip=()):
    """{(method, path): [file:line, ...]} for one caller at `commit`."""
    repo = os.path.expanduser(caller["repo"])
    folder = caller.get("folder", "")
    bases = list(caller.get("bases") or [])
    patterns = [re.compile(p) for p in caller.get("patterns") or []]
    if not bases and not patterns:
        raise ContractError(f"{caller.get('name') or repo}: give `bases` or `patterns` to find its calls")
    strip = (caller.get("strip") or "").rstrip("/")
    found = {}
    with tempfile.TemporaryDirectory() as tmp:
        snapshot(repo, commit, tmp, folder)
        for d, dirs, files in os.walk(os.path.join(tmp, folder)):
            dirs[:] = sorted(x for x in dirs if x not in routes.SKIP_DIRS)
            for f in sorted(files):
                full = os.path.join(d, f)
                rel = os.path.relpath(full, tmp)
                if not f.endswith(CODE) or any(rel == s or rel.startswith(s + "/") for s in skip):
                    continue
                if not caller.get("tests") and routes.is_test("/" + rel):
                    continue
                text = open(full, encoding="utf-8", errors="replace").read()
                for method, path, line, _ in find_calls(text, bases, patterns):
                    if strip and path.startswith(strip + "/"):
                        path = path[len(strip):]
                    found.setdefault((method, path), []).append(f"{rel}:{line}")
    return found


# ---- pins

def resolve_pin(caller, caller_commit, target_repo, target_commit, pin):
    """Where a caller's pinned copy of the target sits, and how far behind the target's commit it is."""
    repo = os.path.expanduser(caller["repo"])
    path = pin["path"].strip("/")
    entry = git(repo, "ls-tree", caller_commit, "--", path)
    if not entry:
        raise ContractError(f"{caller.get('name') or repo}: nothing at {path} in {caller_commit[:9]}")
    mode, kind, obj = entry.split(None, 3)[:3]
    info = {"path": path, "kind": "submodule" if mode == "160000" else "vendored", "commit": None,
            "behind": None, "ahead": None, "problem": None}
    if mode == "160000":
        info["commit"] = obj
    elif kind == "tree":
        commit = pin.get("commit")
        if not commit:
            try:
                stamp = git(repo, "show", f"{caller_commit}:{path}/VENDORED")
                m = re.search(r"\bcommit\s+([0-9a-f]{7,40})\b", stamp)
                commit = m.group(1) if m else None
            except ContractError:
                commit = None
        info["commit"] = commit
    else:
        raise ContractError(f"{caller.get('name') or repo}: {path} is a file, not a submodule or a folder")
    if not info["commit"]:
        info["problem"] = "no pinned commit: give pin.commit or a `commit <sha>` line in its VENDORED file"
        return info
    try:
        full = git(target_repo, "rev-parse", "--verify", "--quiet", info["commit"] + "^{commit}")
    except ContractError:
        full = ""
    if not full:
        info["problem"] = f"pinned commit {info['commit'][:9]} is not in the target repository (fetch it there)"
        if info["kind"] == "vendored":
            info["problem"] += "; its routes are read from the vendored copy"
        return info
    info["commit"] = full
    info["behind"] = int(git(target_repo, "rev-list", "--count", f"{full}..{target_commit}"))
    info["ahead"] = int(git(target_repo, "rev-list", "--count", f"{target_commit}..{full}"))
    return info


def pin_routes(caller, caller_commit, target, info, cache):
    """Served routes at the pin: the target repository at the pinned commit, else the vendored copy itself."""
    folder = info.get("folder", target.get("folder", ""))
    if info["behind"] is not None:
        return target_routes(target, info["commit"], cache, folder=folder, label=f"the pin {info['commit'][:9]}")
    if info["kind"] == "vendored" and not target.get("openapi"):
        inner = os.path.join(info["path"], folder).rstrip("/.")
        with tempfile.TemporaryDirectory() as tmp:
            snapshot(os.path.expanduser(caller["repo"]), caller_commit, tmp, inner)
            return Served(routes.collect(tmp, inner), f"the vendored copy in {info['path']}")
    return None


# ---- the check

def known_failures(caller):
    """{"METHOD /path": why} for failures already reported to their owner: shown, not failed on."""
    out = {}
    for k in caller.get("known") or []:
        route, why = (k, "") if isinstance(k, str) else (k.get("route", ""), k.get("why", ""))
        out[" ".join(route.split())] = why
    return out


def check(contracts, strict=False):
    cache, report, failures = {}, {"contracts": [], "failures": 0, "known": 0}, 0
    for c in contracts.get("contracts", []):
        target = c["target"]
        trepo = os.path.expanduser(target["repo"])
        tcommit = git(trepo, "rev-parse", "--verify", (target.get("commit") or "HEAD") + "^{commit}")
        served = target_routes(target, tcommit, cache)
        crep = {"name": c.get("name"), "target": {"repo": target["repo"], "commit": tcommit, "routes": len(served.rows)},
                "callers": []}
        print(f"\n== {c.get('name') or target['repo']}: {target['repo']} at {tcommit[:9]}"
              f"{' (' + (target.get('folder') or target.get('openapi')) + ')' if target.get('folder') or target.get('openapi') else ''}"
              f", {len(served.rows)} served routes")
        for caller in c.get("callers", []):
            crepo = os.path.expanduser(caller["repo"])
            ccommit = git(crepo, "rev-parse", "--verify", (caller.get("commit") or "HEAD") + "^{commit}")
            pin = caller.get("pin")
            info = resolve_pin(caller, ccommit, trepo, tcommit, pin) if pin else None
            if info:
                info["folder"] = pin.get("folder", target.get("folder", ""))
            at_pin = pin_routes(caller, ccommit, target, info, cache) if info else None
            calls = caller_calls(caller, ccommit, skip=[info["path"]] if info else [])
            rep = {"name": caller.get("name"), "repo": caller["repo"], "commit": ccommit, "calls": [], "pin": info,
                   "failures": 0, "known": 0}
            known, still = known_failures(caller), set()
            print(f"\n-- {caller.get('name') or caller['repo']} ({caller['repo']} at {ccommit[:9]}): "
                  f"{sum(len(v) for v in calls.values())} call(s) to {len(calls)} route(s)")
            for (method, path), sites in sorted(calls.items(), key=lambda kv: (kv[0][1], kv[0][0] or "")):
                row = {"method": method, "path": path, "sites": sites}
                verdicts = [("target", served)] + ([("pin", at_pin)] if at_pin else [])
                bad = []
                for side, srv in verdicts:
                    status, rows = srv.check(method, path)
                    row[side] = status
                    if status == "missing":
                        bad.append(f"not served at {srv.label}")
                        row[side + "_hints"] = [f"{m} {p}" for m, p, _, _ in rows]
                    elif status == "method":
                        bad.append(f"served at {srv.label} only as {', '.join(sorted({r[0] for r in rows}))}")
                    else:
                        row[side + "_at"] = rows[0][2]
                key = f"{method or 'ANY'} {path}"
                is_known = bool(bad) and key in known and not strict
                if bad and key in known:
                    still.add(key)
                    row["known"] = known[key]
                mark = "✗ known" if is_known else "✗" if bad else "✓"
                where = sites[0] + (f" (+{len(sites) - 1} more)" if len(sites) > 1 else "")
                print(f"   {mark:7} {method or 'ANY':6} {path:44} {where}")
                for b in bad:
                    print(f"       {b}")
                hints = row.get("target_hints") or row.get("pin_hints")
                if bad and hints:
                    print(f"       served nearby: {'; '.join(hints)}")
                if is_known and known[key]:
                    print(f"       known: {known[key]}")
                rep["known"] += is_known
                rep["failures"] += bool(bad) and not is_known
                rep["calls"].append(row)
            for key in sorted(set(known) - still):
                print(f"   ✗ {key} is listed as a known failure but no longer fails: remove it from `known`")
                rep["failures"] += 1
            if info:
                if info["problem"]:
                    print(f"   {'✗' if at_pin is None else '·'} pin {info['path']} ({info['kind']}): {info['problem']}")
                    rep["failures"] += at_pin is None
                else:
                    lag = f"{info['behind']} commit(s) behind {tcommit[:9]}" + (f", {info['ahead']} ahead" if info["ahead"] else "")
                    late = pin.get("max_behind") is not None and info["behind"] > pin["max_behind"]
                    print(f"   {'✗' if late else '·'} pin {info['path']} ({info['kind']}) at {info['commit'][:9]}: {lag}"
                          + (f", more than the {pin['max_behind']} allowed" if late else ""))
                    rep["failures"] += late
            if not calls:
                print("   no calls found: check `bases` and `patterns`")
            failures += rep["failures"]
            report["known"] += rep["known"]
            crep["callers"].append(rep)
        report["contracts"].append(crep)
    report["failures"] = failures
    return report


def through_mirrors(contracts, private):
    """The contracts with every repository the drift watch mirrors read from its mirror."""
    mirrors, by_clone = os.path.join(private, "mirrors"), {}
    for name in sorted(os.listdir(mirrors)) if os.path.isdir(mirrors) else []:
        clones = os.path.join(private, name.removesuffix(".clones.json"), "clones.json")
        if not name.endswith(".clones.json") or not os.path.isfile(clones):
            continue
        with open(clones, encoding="utf-8") as f:
            paths = json.load(f)
        with open(os.path.join(mirrors, name), encoding="utf-8") as f:
            mirrored = json.load(f)
        for key, path in paths.items():
            if key in mirrored:
                by_clone[os.path.realpath(os.path.expanduser(path))] = mirrored[key]
    for contract in contracts["contracts"]:
        for side in [contract["target"], *contract["callers"]]:
            side["repo"] = by_clone.get(os.path.realpath(os.path.expanduser(side["repo"])), side["repo"])
    return contracts


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("contracts")
    ap.add_argument("--out")
    ap.add_argument("--strict", action="store_true", help="fail on known failures too")
    ap.add_argument("--mirrors", metavar="PRIVATE", help="read each repository from the drift watch's mirror in PRIVATE/mirrors")
    a = ap.parse_args()
    try:
        contracts = json.load(open(os.path.expanduser(a.contracts)))
        if a.mirrors:
            contracts = through_mirrors(contracts, os.path.expanduser(a.mirrors))
        report = check(contracts, strict=a.strict)
    except (ContractError, OSError, ValueError) as exc:
        print(f"contracts: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyError as exc:
        print(f"contracts: a contract or caller lacks the key {exc}", file=sys.stderr)
        sys.exit(2)
    if a.out:
        json.dump(report, open(a.out, "w"), indent=1)
    n, k = report["failures"], report["known"]
    known = f" ({k} known failure(s), reported above)" if k else ""
    print(f"\n{'all contracts hold' if not n else f'{n} contract check(s) failed'}{known}")
    sys.exit(1 if n else 0)


if __name__ == "__main__":
    main()
