"""Write one brief per mapping agent from an areas file.

usage: python3 -I pipeline/brief.py AREAS.json

The areas file (keep it in the private folder: it names the client's paths):

  {"map": "<private>/<map>", "checkout": "/tmp/checkout", "out": "/tmp/briefs",
   "slices": "/tmp/slices", "routes": {"<service>": "routes-<service>.json"},
   "areas": {
     "<area>": {"kind": "code", "app": "<repo folder>/", "service": "<service>",
                "parents": ["<skeleton id>"], "prefixes": ["<group prefix>"], "budget": 150,
                "own": ["<repo folder>/src/", "<repo folder>/main.py"], "exclude": [],
                "start": "the docs to read first", "must": ["..."], "flows": ["..."]},
     "<engagement area>": {"kind": "engagement", "engagement": "<slug>", "name": "<display name>",
                "repo": "~/path/to/clone", "app": "<repo folder>/", "start": "...", "extra": "..."}}}

For code areas it checks that no file is owned twice and lists files nobody owns, so every file gets
at most one box. Each brief is the playbook's template, filled in: SCHEMA and skeleton first, owned
files, other areas' files, the routes in the area's files, the must-cover list, flows, the rules, the
validate command, and the reply format (findings with path:line). Agents write slices to "slices";
validate, merge with refs.py, then copy them into the map's parts/.
"""
import json
import os
import sys

TOPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(TOPO, "pipeline"))
import depthcheck  # noqa: E402
STEPS = "intake, sources, context, dashboard, analysis, mapping, buildout, delivery, reuse"

RULES = """## Rules
- Read-only everywhere: never edit, create or delete anything in the checkout or a repository; never run its
  code, install packages or change git state. Only read files and write your slice.
- Never copy secrets, tokens or keys, even from example or env files.
- Never quote business figures (prices, fees, revenue, user counts, test results); describe them
  qualitatively. Technical numbers (timeouts, ports, thresholds, model parameters) are fine.
- No person names anywhere; use roles. Client, company and product names only where a path or the code holds
  them; list every one you wrote in your reply.
- Plain, specific English; spell out acronyms on first use in each summary and detail; no em dashes.
"""


def files_under(checkout, prefix):
    root = os.path.join(checkout, prefix)
    if os.path.isfile(root):
        return [prefix]
    return sorted(os.path.relpath(os.path.join(d, f), checkout) for d, _, fs in os.walk(root) for f in fs)


def collapse(owned, every):
    """Whole folders an area owns become one line."""
    out, done, owned_set = [], set(), set(owned)
    for f in sorted(owned):
        parts = f.split("/")
        for depth in range(2, len(parts)):
            d = "/".join(parts[:depth]) + "/"
            if d in done:
                break
            inside = [x for x in every if x.startswith(d)]
            if len(inside) > 1 and all(x in owned_set for x in inside):
                out.append(f"{d}  (all {len(inside)} files)")
                done.add(d)
                break
        else:
            out.append(f)
    return sorted(set(out))


def code_brief(name, a, cfg, owned, others, routes):
    mine = [r for r in routes.get(a.get("service"), []) if r[2].split(":")[0] in owned]
    every = cfg["_every"]
    defs = {p: n for p, n in cfg["_defs"].items() if p in owned}
    count = sum(len(n) for n in defs.values())
    level = cfg["_level"]
    excerpts = f"{level['excerpts']} to {level['excerpts'] + max(2, level['excerpts'] // 2)}" if level["excerpts"] else "a few"
    intro = f"- Depth: this map is made at depth `{level['name']}`: {level['about']}.\n"
    if not level["symbols"]:
        depth = intro + ("- Give every module and file that matters a box, and symbol boxes (cited at path:line) only to "
                         "the entry points and the main mechanisms, a few per module at most. Connect the files to each "
                         "other and to outside services; the depth check counts a file as connected when it, or a box "
                         "inside it, has a connection.\n")
    elif not count:
        depth = intro
    elif cfg["_full"]:
        depth = intro + (f"- Public definitions: the {count} public classes, functions and types in your files, and the public "
                 f"methods of those classes (Class.method), each get a symbol box (f:<path>#<name>, or "
                 f"f:<path>#<Class>.<method>) cited at the line that defines them; fold only trivial ones (a getter, a "
                 f"one-line wrapper) into their parent. The map's depth check fails under {level['symbols']:.0%}. "
                 f"They are:\n" + "\n".join(f"  {p}: {', '.join(n)}" for p, n in sorted(defs.items())) + "\n")
    else:
        need = depthcheck.symbols_needed(count, level)
        depth = intro + (f"- Public definitions: your files define {count}, too many to box them all. Give at least {need} of "
                 f"them a symbol box (f:<path>#<name>, cited at path:line): the entry points, the core mechanisms, "
                 f"what other areas call, and the public methods that do the work. The map's depth check counts "
                 f"them per area.\n")
    return f"""You are mapping one slice of a codebase for Topo, an interactive, zoomable architecture map. You write
structured claims with evidence into one JSON slice file; scripts check every claim.

FIRST read {TOPO}/pipeline/SCHEMA.md and {cfg['map']}/skeleton.json completely. Follow SCHEMA.md exactly
(fields, length limits, id families). This brief is everything else you need: you don't need the playbook.

Checkout (read-only): {cfg['checkout']}. Every path you write is relative to that folder{f' and starts with "{a["app"]}"' if a.get('app') else ''}.
The code is the source of truth; documents are orientation. Start with: {a.get('start', 'the README and entry points')}.

## Your area: `{name}`
Output: {cfg['slices']}/{name}.json ("area": "{name}"; split into {name}.1.json, {name}.2.json above about 1.2 MB).
Group-id prefixes: {', '.join('`' + p.rstrip('.') + '.`' for p in a.get('prefixes', []))}. Skeleton parents: {', '.join(a.get('parents', []))}.
Node budget: about {a.get('budget', 150)} boxes, plus one endpoint box per route in your files ({len(mine)}, listed below).

Files you OWN ({len(owned)}; create f:/d: nodes only for these):
""" + "\n".join("  " + x for x in collapse(owned, every)) + """

Other areas own (reference by predictable id, never create nodes for them):
""" + ("\n".join(f"  {n}: " + "; ".join(v[:12]) + (" ..." if len(v) > 12 else "") for n, v in others.items()) or "  (none: yours is the only area)") + """

## Must cover
""" + "\n".join(f"{i}. {m}" for i, m in enumerate(a.get("must", []), 1)) + f"""
{depth}- Tests: one test node per test file you own, with a tests edge to the code it exercises.
- Calls to other areas by predictable ids; outside services by their x: ids in the skeleton (a missing one:
  point at the nearest ext.* group and name it in your reply).
- {excerpts} verbatim code excerpts (at most 15 lines each) for the functions that carry the logic.
- Every symbol box cites its line: the first path is path:line or path:start-end, never the bare file.
- Connections: draw what the code does between your own boxes too (calls, reads, writes, what a class
  extends or wraps), not only across areas. The depth check fails when more than {100 - round(depthcheck.CONNECTED_FLOOR * 100)}% of the
  {'file' if level['connect'] == 'files' else 'symbol'} boxes have no connection, or when there are fewer than {level['excerpts']} excerpts.
- Findings: besides what you notice while mapping, check the code examples in the docs you read and the
  build, test and coverage settings in the manifests against the code, and report every mismatch.
- Flows (2 to 3, ids flow.{name}.<slug>): {'; '.join(a.get('flows', [])) or 'the main paths through your area'}.

## Ids and endpoints
- Endpoints: ep:{a.get('service', '<service>')} <METHOD> <path>, exactly as declared. Route lists for every service:
  {', '.join(cfg.get('routes', {}).values()) or '(none)'}.
- A call to a route no server declares: still use its ep: id and say so in the detail; it becomes a contract finding.
- Group ids of other areas cannot be validated from your slice; point at their file or folder instead.

{RULES}- Before finishing, re-open the files behind your 10 most important nodes and check every claim.
- Validate until OK: python3 -I {TOPO}/pipeline/validate.py {cfg['map']} {cfg['slices']}/{name}*.json --repo {cfg['checkout']}

## Final reply (at most 250 words; no JSON)
Counts, part files, cross-area and cross-application references, outside services missing from the skeleton,
names written, anything unsure, and FINDINGS (defects, doc-versus-code mismatches, dead code, committed
secrets) with path:line, saying which you verified by re-reading the code.

## Routes in your files ({len(mine)})
""" + "\n".join(f"  {m} {p}   {loc}" for m, p, loc in mine) + "\n"


def engagement_brief(name, a, cfg):
    e = a["engagement"]
    return f"""You are mapping one client engagement for Topo as the ACTIONS WE TOOK to do the job: the outside sources we
pulled, the pipelines and dashboards we built, the analyses and memos we delivered, the tools and agents we used,
and what we carried forward. Each action is a box filed under one step of our unified process.

FIRST read {TOPO}/pipeline/SCHEMA.md (note phase, date and capabilities), {cfg['map']}/skeleton.json (the process
steps proc.*, your step groups eng.{e}.*, the outside services x:*), and the "process" and "capabilities" keys of
{cfg['map']}/topo.config.json.

Engagement: {a.get('name', e)}. Snapshot (read-only): {cfg['checkout']}/{a.get('app', '').rstrip('/')}
History: read-only git commands on {a.get('repo', 'the clone')}. Start with: {a.get('start', 'the README and status documents')}.
{a.get('extra', '')}

## Output
{cfg['slices']}/{name}.json with "area": "{name}". Parents: eng.{e}.<step>, step one of: {STEPS}.
Ids: eng.{e}.<step>.<slug>. Never create f:, d:, ep: or mcp: nodes: connect to existing ones
({cfg.get('ids', 'grep the map parts for ids')}). Budget: 60 to 120 actions.

## Each action
kind (job, workflow, component, doc, data, service, config, agent); name (at most 48 characters); summary (what
we did and why it mattered); detail (how, what it fed, the outcome, without figures); date (YYYY-MM-DD, from the
commit that added it or the document's name); phase; capabilities (1 to 4 from the vocabulary; name missing ones in
your reply); paths (files that show it, starting "{a.get('app', '')}"); status only with evidence; up to 5 facts.

## Connections (each with evidence path:line)
reads (outside sources, data), generates (pull -> data file -> tab), calls / configures (the platforms and other
systems the work used), deploys, triggers. When the evidence shows something came from another engagement, draw generates from
that engagement's step group (eng.<other>.<step>) to your action.

## Must cover
Intake; every outside source and how we read it, the registry and the pull end to end; context; the dashboard,
one action per tab; analyses, one per dated memo; build-out; delivery; carry forward. One flow,
flow.eng-{e}.story, 8 to 14 steps in date order.

{RULES}- Validate until OK: python3 -I {TOPO}/pipeline/validate.py {cfg['map']} {cfg['slices']}/{name}*.json --repo {cfg['checkout']}

## Final reply (at most 300 words; no JSON)
Counts by step, the flow, sources missing from the skeleton, capability tags you needed, connections to other
engagements and systems, and OPPORTUNITIES: what this engagement has that others lack, or lacks that they have.
"""


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cfg = json.load(open(sys.argv[1]))
    for k in ("map", "checkout", "out", "slices"):
        cfg[k] = os.path.expanduser(cfg[k])
    os.makedirs(cfg["out"], exist_ok=True)
    os.makedirs(cfg["slices"], exist_ok=True)
    routes = {s: json.load(open(os.path.expanduser(p))) for s, p in cfg.get("routes", {}).items()}
    code = {n: a for n, a in cfg["areas"].items() if a.get("kind", "code") == "code"}
    apps = sorted({a.get("app", "") for a in code.values()})
    every = sorted(f for app in apps for f in files_under(cfg["checkout"], app))
    cfg["_every"] = every
    cfg["_defs"] = {p: n for p, n in depthcheck.public_defs(cfg["checkout"]).items() if p in set(every)}
    code_areas = sum(1 for a in cfg["areas"].values() if a.get("kind", "code") == "code")
    cfg["_level"] = depthcheck.map_level(cfg["map"])
    import init   # imported here: it reads this machine's settings
    code_files = sum(1 for f in every if init.LANGS.get(f.rsplit(".", 1)[-1].lower()) not in (None, *init.NOT_CODE)
                     and not set(f.split("/")) & init.VENDORED)
    suggested = init.agents_at(cfg["_level"], code_files, sum(len(n) for n in cfg["_defs"].values()))
    most = max(int(x) for x in __import__("re").findall(r"\d+", suggested))
    if code_areas > most:
        print(f"MORE AREAS THAN SUGGESTED: {code_areas} code areas where depth {cfg['_level']['name']} suggests {suggested}. "
              f"Every area is a mapping agent and adds to what the depth check asks, so the map costs more; "
              f"tell the user why before going on, or merge areas.")
    cfg["_full"] = depthcheck.full_depth(sum(len(n) for n in cfg["_defs"].values()), max(1, code_areas), cfg["_level"])
    owned = {}
    for n, a in code.items():
        fs = set()
        for p in a.get("own", []):
            fs |= set(files_under(cfg["checkout"], p))
        owned[n] = sorted(f for f in fs if not any(f.startswith(x) for x in a.get("exclude", [])))
    seen, problems = {}, 0
    for n, fs in owned.items():
        for f in fs:
            if f in seen:
                print(f"OWNED TWICE {f}: {seen[f]} and {n}")
                problems += 1
            seen[f] = n
    unowned = [f for f in every if f not in seen]
    if unowned:
        print(f"{len(unowned)} file(s) nobody owns (fine for trivia, not for code):")
        for f in unowned[:30]:
            print("  " + f)
    for n, a in cfg["areas"].items():
        if a.get("kind", "code") == "code":
            others = {m: collapse(owned[m], every) for m in code if m != n}
            text = code_brief(n, a, cfg, set(owned[n]), others, routes)
        else:
            text = engagement_brief(n, a, cfg)
        path = os.path.join(cfg["out"], f"{n}.md")
        open(path, "w").write(text)
        print(f"  {n:24} {len(owned.get(n, [])):5} files  -> {path}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
