"""Start a map: its folder, config, skeleton, orientation notes and read-only checkout.

usage: python3 -I pipeline/init.py REPO [REPO ...] [--name NAME] [--title TITLE] [--out DIR]
                                  [--depth overview|standard|deep|<a depth of this machine's>]

Each REPO is a local git clone or a git URL; a URL is cloned once, shallow, into DIR/clones/. The map
folder (default ~/topo-maps/<name>, outside this repository) gets:

  topo.config.json  the title, one region per application and one for outside services, and every
                    repository at its HEAD commit, with links into the code when its remote is on
                    GitHub, GitLab or Bitbucket
  skeleton.json     one app: box per repository and the outside-services region (add the subsystems)
  clones.json       where each repository is cloned on this machine (checkout.py and drift.py read it)
  checkout/         every repository's committed files at that commit, from git archive: the read-only
                    folder mapping agents read and `validate.py --repo` checks against
  ORIENT.md         per repository: languages, the largest folders, manifests, entry points and docs,
                    and how many mapping agents its size suggests

Only committed files are mapped, and nothing in a clone is changed: a clone with uncommitted changes
gets a warning. It stops if DIR already holds a map (refresh that one with the refresh skill).
"""
import argparse
import datetime
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import settings  # noqa: E402
LANGS = {
    "py": "Python", "ts": "TypeScript", "tsx": "TypeScript", "js": "JavaScript", "jsx": "JavaScript",
    "mjs": "JavaScript", "cjs": "JavaScript", "go": "Go", "rs": "Rust", "java": "Java", "kt": "Kotlin",
    "kts": "Kotlin", "scala": "Scala", "rb": "Ruby", "php": "PHP", "cs": "C#", "fs": "F#", "swift": "Swift",
    "m": "Objective-C", "c": "C", "h": "C", "cc": "C++", "cpp": "C++", "hpp": "C++", "ex": "Elixir",
    "exs": "Elixir", "erl": "Erlang", "clj": "Clojure", "hs": "Haskell", "ml": "OCaml", "dart": "Dart",
    "lua": "Lua", "r": "R", "jl": "Julia", "vue": "Vue", "svelte": "Svelte", "sql": "SQL", "sh": "Shell",
    "tf": "Terraform", "proto": "Protocol Buffers", "graphql": "GraphQL", "gql": "GraphQL", "sol": "Solidity",
    "zig": "Zig", "nim": "Nim", "html": "HTML", "css": "CSS", "scss": "CSS",
}
NOT_CODE = {"CSS"}   # counted as a language, not toward the size of the mapping
MANIFESTS = re.compile(r"^(package\.json|pnpm-workspace\.yaml|turbo\.json|nx\.json|lerna\.json|pyproject\.toml|setup\.py|"
                       r"requirements[\w.-]*\.txt|Pipfile|go\.mod|Cargo\.toml|pom\.xml|build\.gradle(\.kts)?|Gemfile|"
                       r"composer\.json|[\w.-]+\.csproj|[\w.-]+\.sln|mix\.exs|pubspec\.yaml|Package\.swift|Dockerfile[\w.-]*|"
                       r"(docker-)?compose[\w.-]*\.ya?ml|Procfile|serverless\.ya?ml|vercel\.json|netlify\.toml|fly\.toml|"
                       r"app\.yaml|Chart\.yaml|Makefile|[\w.-]+\.tf)$")
ENTRIES = re.compile(r"^(main|app|server|index|manage|wsgi|asgi|cli|__main__|Program|Main|Application)\.(py|js|ts|go|rs|cs|java|kt|rb)$")
DOCS = re.compile(r"^(README|ARCHITECTURE|DESIGN|CONTRIBUTING|OVERVIEW)[\w.-]*$", re.I)
VENDORED = {"node_modules", "vendor", "third_party", "third-party", "dist", "build", "external"}
HUES = [262, 189, 38, 140, 330, 20, 100, 290, 60, 170]


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout.strip()


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "repo"


def is_url(s):
    return bool(re.match(r"^(https?|ssh|git|file)://|^[\w.-]+@[\w.-]+:", s))


def web_remote(remote):
    """(host, web address, 'owner/name') for a remote on GitHub, GitLab (gitlab.com, or a server whose name
    starts with gitlab.) or Bitbucket, in any of its forms, else None. Credentials and ports never survive.
    host is what the viewer needs to shape links into the code: "github", "gitlab" or "bitbucket"."""
    m = re.match(r"^(?:https?://(?:[^@/]+@)?|ssh://[^@/]+@|[\w.-]+@)([\w.-]+?)(?::\d+)?[:/]((?:[\w.-]+/)+?[\w.-]+?)(?:\.git)?/?$",
                 remote or "")
    if not m:
        return None
    server, path = m.group(1).lower(), m.group(2)
    if server == "github.com" and path.count("/") == 1:
        host = "github"
    elif server == "gitlab.com" or server.startswith("gitlab."):
        host = "gitlab"   # GitLab groups nest, so the path can have more than two parts
    elif server == "bitbucket.org" and path.count("/") == 1:
        host = "bitbucket"
    else:
        return None
    return host, f"https://{server}/{path}", path


def first_sentence(checkout):
    """The README's first sentence of prose, as a starting summary (the mapping rewrites it)."""
    for name in sorted(os.listdir(checkout)) if os.path.isdir(checkout) else []:
        if not re.match(r"^readme(\.md|\.rst|\.txt)?$", name, re.I):
            continue
        text = open(os.path.join(checkout, name), encoding="utf-8", errors="replace").read()
        for para in re.split(r"\n\s*\n", text):
            p = " ".join(para.split())
            if len(p) < 40 or p.startswith(("#", "!", "[", "<", "|", "```", "=", "-", "*", ">")):
                continue
            p = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", p).replace("**", "").replace("`", "")
            m = re.match(r"^(.{30,200}?[.!?])(\s|$)", p)
            return m.group(1) if m else p[:197].rsplit(" ", 1)[0] + "..."
    return None


def survey(root):
    """What a checkout holds: languages, folder sizes, manifests, entry points and docs."""
    langs, top, sub, manifests, entries, docs = Counter(), Counter(), Counter(), [], [], []
    files = code = 0
    for d, dirs, fs in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        rel = os.path.relpath(d, root)
        parts = [] if rel == "." else rel.split(os.sep)
        for f in fs:
            files += 1
            lang = LANGS.get(f.rsplit(".", 1)[-1].lower()) if "." in f else None
            is_code = bool(lang) and lang not in NOT_CODE and not (set(parts) & VENDORED)
            if lang:
                langs[lang] += 1
            code += is_code
            key = parts[0] + "/" if parts else "(top level)"
            top[key] += is_code
            if len(parts) >= 2:
                sub["/".join(parts[:2]) + "/"] += is_code
            path = "/".join(parts + [f])
            if len(parts) <= 3 and MANIFESTS.match(f) and not (set(parts) & VENDORED):
                manifests.append(path)
            if len(parts) <= 3 and ENTRIES.match(f) and not (set(parts) & VENDORED):
                entries.append(path)
            if len(parts) <= 1 and DOCS.match(f):
                docs.append(path)
        if parts == ["docs"] or parts == ["doc"]:
            docs.append(rel + "/")
    return {"files": files, "code": code, "langs": langs, "top": top, "sub": sub,
            "manifests": manifests, "entries": entries, "docs": docs}


def agents_for(code):
    """How many mapping agents a code size suggests (each maps about 100 to 300 boxes)."""
    for limit, n in ((120, "1"), (400, "2 to 3"), (1200, "4 to 6"), (3000, "6 to 10")):
        if code <= limit:
            return n
    return "10 to 14 (or map the core and leave the rest as labelled regions)"


def agents_at(level, code, defs):
    """How many mapping agents a map needs at a depth (a full level from depths.py), as text."""
    import depths
    return depths.agents(level, code, defs, agents_for(code))


def orient(repos, surveys, total, level, defs=0):
    import depths
    kind = level["agents"]
    per = (f"about {kind[1]} code files" if kind[0] == "code_files" else
           f"about {kind[1]} public definitions" if kind[0] == "public_definitions" else "about 100 to 300 boxes")
    L = [f"# Orientation\n",
         f"Read this before drawing the skeleton. Counts are committed files in `checkout/`; code files leave out "
         f"CSS and folders that look vendored ({', '.join(sorted(VENDORED))}).\n",
         f"**Depth:** {level['name']}: {level['about']} ({depths.floors(level)}; init.py --depth sets it, "
         f"`python3 -I pipeline/depths.py` lists the depths, and the depth check holds the map to it).\n",
         f"**Size:** {total:,} code files in all, {defs:,} public definitions outside tests. **Suggested mapping "
         f"agents:** {agents_at(level, total, defs)}, one per area of {per}. They run in parallel; each takes about "
         f"15 to 35 minutes.\n"]
    for r, s in zip(repos, surveys):
        L.append(f"## {r['name']} (`{r['key']}`)\n")
        where = f"paths start with `{r['prefix']}`" if r.get("prefix") else "paths start at the checkout's root"
        L.append(f"- Commit `{r['commit'][:12]}`, last committed {r['date']}; {where}.")
        L.append(f"- {s['files']:,} files, {s['code']:,} of them code. Languages: "
                 + (", ".join(f"{k} {v:,}" for k, v in s["langs"].most_common(8)) or "none recognised") + ".")
        if s["docs"]:
            L.append(f"- Docs to start from: " + ", ".join(f"`{d}`" for d in s["docs"][:12]) + ".")
        L.append("\nLargest folders by code files:\n")
        for folder, n in s["top"].most_common(12):
            if not n:
                continue
            inner = [(k, v) for k, v in s["sub"].most_common() if k.startswith(folder) and v][:6]
            L.append(f"- `{folder}` {n:,}" + (": " + ", ".join(f"`{k[len(folder):]}` {v:,}" for k, v in inner) if inner else ""))
        if s["manifests"]:
            L.append("\nManifests and deploy files (they name the applications, services and outside systems):\n")
            L += [f"- `{m}`" for m in s["manifests"][:30]]
            if len(s["manifests"]) > 30:
                L.append(f"- and {len(s['manifests']) - 30} more")
        if s["entries"]:
            L.append("\nLikely entry points:\n")
            L += [f"- `{e}`" for e in s["entries"][:20]]
        L.append("")
    return "\n".join(L) + "\n"


def layout(repos, surveys):
    """Applications side by side, widths by code size, outside services in a band along the bottom."""
    n = len(repos)
    # at least as wide as the example's world: a layout narrower than the window gets stretched to fit
    # it, and a view someone zoomed into would then shift on every resize
    width = min(2600 + 700 * max(n - 3, 0), 4600)
    gap = 80
    weights = [math.sqrt(max(s["code"], 1)) for s in surveys]
    weights = [max(w, 0.3 * max(weights)) for w in weights]   # a small application still gets room to read
    usable = width - gap * (n - 1)
    regions, x = [], 0.0
    for i, (r, w) in enumerate(zip(repos, weights)):
        x1 = width if i == n - 1 else x + usable * w / sum(weights)
        regions.append({"id": r["key"], "rect": [round(x), 0, round(x1), 1000], "hue": HUES[i % len(HUES)], "sat": 40})
        x = x1 + gap
    regions.append({"id": "ext", "rect": [0, 1100, width, 1420], "hue": 212, "sat": 14})
    return regions


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("repos", nargs="+", metavar="REPO")
    ap.add_argument("--name", help="the map's folder name (default: the first repository's name)")
    ap.add_argument("--title", help="the map's title (default: the first repository's name)")
    ap.add_argument("--out", help="the map folder (default ~/topo-maps/<name>)")
    ap.add_argument("--depth", help="how deep the map goes: overview, standard, deep, or a depth this machine "
                                    "defines (default: the machine's setting, else standard)")
    a = ap.parse_args()

    # resolve every repository first: a URL is cloned, a path is read where it is
    specs = []
    for spec in a.repos:
        if is_url(spec):
            base = re.sub(r"\.git/?$", "", spec.rstrip("/")).rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            specs.append((spec, None, base))
            continue
        path = os.path.abspath(os.path.expanduser(spec))
        try:
            top = git(path, "rev-parse", "--show-toplevel")
            git(top, "rev-parse", "HEAD")
        except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
            sys.exit(f"init: {spec} is not a git repository with at least one commit")
        specs.append((spec, top, os.path.basename(top)))
    name = slug(a.name or specs[0][2])
    out = os.path.abspath(os.path.expanduser(a.out or os.path.join("~", "topo-maps", name)))
    if os.path.exists(os.path.join(out, "topo.config.json")):
        sys.exit(f"init: {out} already holds a map; refresh it with the refresh skill (/topo:refresh), or pass a new --out")
    if os.path.isdir(os.path.join(out, "checkout")) and os.listdir(os.path.join(out, "checkout")):
        sys.exit(f"init: {out}/checkout exists and is not empty; remove it or pass a new --out")
    os.makedirs(out, exist_ok=True)

    repos, clones, keys = [], {}, set()
    for spec, top, base in specs:
        key = "app:" + slug(base)
        while key in keys:
            key += "-2"
        keys.add(key)
        if top is None:
            top = os.path.join(out, "clones", key[4:])
            if not os.path.isdir(top):
                print(f"  cloning {spec} (shallow) -> {top}")
                r = subprocess.run(["git", "clone", "--quiet", "--depth", "1", spec, top], capture_output=True, text=True)
                if r.returncode:
                    sys.exit(f"init: could not clone {spec}: {r.stderr.strip()}")
        commit = git(top, "rev-parse", "HEAD")
        if git(top, "status", "--porcelain", "--untracked-files=no"):
            print(f"  warning {base}: uncommitted changes are not mapped (only commit {commit[:12]} is)")
        branch = git(top, "rev-parse", "--abbrev-ref", "HEAD")
        remote = ""
        try:
            remote = git(top, "remote", "get-url", "origin")
        except subprocess.CalledProcessError:
            pass
        web = web_remote(remote)
        where = web[2] if web else None
        date = git(top, "log", "-1", "--format=%cs")
        repos.append({"key": key, "name": base, "url": web[1] if web else None, "commit": commit,
                      "note": f"mapped from its source code ({where or base} {branch}, last commit {date}).",
                      "date": date, "where": where})
        if web and web[0] != "github":
            repos[-1]["host"] = web[0]
        clones[key] = top
    if len(repos) > 1:
        for r in repos:
            r["prefix"] = r["key"][4:] + "/"

    json.dump(clones, open(os.path.join(out, "clones.json"), "w"), indent=1)
    month = datetime.date.today().strftime("%B %Y")
    import depths
    try:
        level = depths.resolve(a.depth or settings.depth())
    except depths.DepthError as e:
        sys.exit(f"init: {e}")
    config = {
        "title": a.title or (repos[0]["name"] if len(repos) == 1 else name),
        "generated": f"{datetime.date.today().day} {month}",
        "repos": [{k: r[k] for k in ("key", "name", "url", "host", "commit", "prefix", "note") if k in r} for r in repos],
        "regions": [],
        "apps": {r["key"]: {"provenance": f"Mapped from source · {month}"} for r in repos},
        "owners": [],
        "endpoint_fallback": {},
        "prefix_fallback": {},
        "area_names": {},
        "depth": depths.stored(level),
    }
    json.dump(config, open(os.path.join(out, "topo.config.json"), "w"), indent=1, ensure_ascii=False)

    checkout = os.path.join(out, "checkout")
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "checkout.py"), out, "--out", checkout],
                       capture_output=True, text=True)
    if r.returncode:
        os.remove(os.path.join(out, "topo.config.json"))
        sys.exit(f"init: checkout failed: {r.stderr.strip() or r.stdout.strip()}")

    surveys = [survey(os.path.join(checkout, r.get("prefix", "").rstrip("/"))) for r in repos]
    config["regions"] = layout(repos, surveys)
    json.dump(config, open(os.path.join(out, "topo.config.json"), "w"), indent=1, ensure_ascii=False)
    nodes = []
    for r, s in zip(repos, surveys):
        summary = first_sentence(os.path.join(checkout, r.get("prefix", "").rstrip("/")))
        node = {"id": r["key"], "parent": None, "name": r["name"], "kind": "app",
                "summary": summary or f"{r['name']}, mapped from its source code."}
        if r["where"]:
            node["repo"] = r["where"]
        nodes.append(node)
    nodes.append({"id": "ext", "parent": None, "name": "Outside services and people", "kind": "group",
                  "summary": "The databases, queues, providers, hosting and people the applications depend on."})
    json.dump({"nodes": nodes}, open(os.path.join(out, "skeleton.json"), "w"), indent=1, ensure_ascii=False)
    os.makedirs(os.path.join(out, "parts"), exist_ok=True)
    total = sum(s["code"] for s in surveys)
    import depthcheck   # imported here: it reads this module's VENDORED
    defs = sum(len(v) for v in depthcheck.public_defs(checkout).values())
    open(os.path.join(out, "ORIENT.md"), "w").write(orient(repos, surveys, total, level, defs))

    for r, s in zip(repos, surveys):
        print(f"  {r['key']:24} {r['commit'][:12]}  {s['code']:,} code files" + (f"  {r['url'][8:]}" if r["url"] else ""))
    print(f"map folder ready: {out}")
    print(f"  depth: {level['name']}; suggested mapping agents: {agents_at(level, total, defs)}")
    print(f"  next: read {os.path.join(out, 'ORIENT.md')}, add subsystems and outside services to skeleton.json,"
          f" then split the work ({os.path.join(os.path.dirname(HERE), 'MAPPING_PLAYBOOK.md')} section 3)")


if __name__ == "__main__":
    main()
