"""Analyze a built map's structure and interconnections for build-out planning.

usage: python3 -I pipeline/analyze.py MAP_DIR [--out MAP_DIR/ANALYSIS.md]   (run build.py first)

Everything here is computed from the map's boxes and connections, so it is only as good as the
mapping: treat it as a structured starting point for a review, not a verdict. Sections:
connections between applications (each one's integration surface in the others), integration
contracts (calls the other side does not serve, version pins, contracts shared by several
applications), capabilities duplicated across applications, coupling between subsystems, hubs,
outside-service concentration, delivery status, test coverage, knowledge gaps, findings recorded
while mapping, and ranked build-out candidates. It also writes BUILDOUT.md next to ANALYSIS.md: a
draft build-out plan generated from the same numbers.
"""
import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict

META_KINDS = {"tests", "documents"}
# hosting, people and databases: every application has its own, so a "client" for them is not duplication
INFRA_GROUPS = {"ext.hosting", "ext.people"}
INFRA_SERVICES = {"x:postgres", "x:qdrant"}
STOP = set("a an and the of to in on for with from by or as at is are be it its this that into over per each one "
           "their them they which what when then than via not no out up all any can".split())
STATUS_ORDER = ["live", "built", "partial", "stub", "planned", "archived", "unknown"]
FINDING = re.compile(
    r"[^.;\n]*\b(gotcha|drift|drifted|stale|disagree|contradict|not built|unimplemented|never (?:runs|read|called|wired|exercised|parsed)|"
    r"is ignored|are ignored|ignores|dead code|orphan|flaky|broken|bug|not wired|not live|data-starved|in-memory only|"
    r"hard-coded|hardcoded|placeholder|unresolved|missing|skips?|bypass)\b[^.;\n]*[.;]?", re.I)


def tok(node_id):
    """The viewer's box token (FNV-1a over UTF-16 code units, base 36), for links into the page."""
    h = 0x811C9DC5
    units = node_id.encode("utf-16-le")
    for k in range(0, len(units), 2):
        h = ((h ^ (units[k] | units[k + 1] << 8)) * 0x01000193) & 0xFFFFFFFF
    digits, out = "0123456789abcdefghijklmnopqrstuvwxyz", ""
    while True:
        h, r = divmod(h, 36)
        out = digits[r] + out
        if not h:
            return "n" + out


def pl(n, one, many=None):
    return f"{n} {one if n == 1 else many or one + 's'}"


def words(text):
    return {w for w in re.findall(r"[a-z][a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def load(mdir):
    d = json.load(open(os.path.join(mdir, "topo-data.json")))
    nodes = {n["id"]: n for n in d["nodes"]}
    kids = defaultdict(list)
    for n in d["nodes"]:
        if n.get("parent"):
            kids[n["parent"]].append(n["id"])
    return d, nodes, kids


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("map_dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    d, nodes, kids = load(a.map_dir)

    def chain(i):
        out = []
        while i:
            out.append(i)
            i = nodes[i].get("parent")
        return out[::-1]

    def at_depth(i, k):
        c = chain(i)
        return c[min(k, len(c) - 1)]

    def unit(i):
        """The file/module-level box a node belongs to (for hub counting)."""
        for x in reversed(chain(i)):
            n = nodes[x]
            if (x.startswith(("f:", "d:")) and "#" not in x) or n["kind"] in ("module", "component", "service", "endpoint", "external", "agent", "workflow", "data", "job"):
                if not (x.startswith("f:") and "#" in x):
                    return x
        return i

    def desc(i):
        out, stack = [], [i]
        while stack:
            x = stack.pop()
            out.append(x)
            stack.extend(kids.get(x, []))
        return out

    name = lambda i: nodes[i]["name"]
    edges = [e for e in d["edges"] if e["from"] in nodes and e["to"] in nodes]
    work = [e for e in edges if e["kind"] not in META_KINDS]
    roots = [i for i, n in nodes.items() if not n.get("parent")]
    subs = [i for i, n in nodes.items() if n.get("parent") in roots]
    L = []
    section = iter(range(1, 100))
    H = lambda title: f"## {next(section)}. {title}\n"

    # ---- overview
    L.append(f"# Analysis: {d['meta'].get('title', 'Topo map')}\n")
    L.append(f"Computed from the map ({len(nodes):,} boxes, {len(edges):,} connections; "
             f"{len(work):,} excluding tests and documentation links). Generated with `pipeline/analyze.py`; "
             "it reflects the mapping, so verify anything you act on in the code.\n")

    # ---- between applications: the integration surface each one depends on in another
    apps = [r for r in roots if nodes[r]["kind"] == "app"]
    app_pair, app_kinds, surface = Counter(), defaultdict(Counter), defaultdict(lambda: defaultdict(Counter))
    for e in work:
        ra, rb = chain(e["from"])[0], chain(e["to"])[0]
        if ra != rb and ra in apps and rb in apps:
            app_pair[(ra, rb)] += 1
            app_kinds[(ra, rb)][e["kind"]] += 1
            surface[(ra, rb)][e["to"]][at_depth(e["from"], 1)] += 1
    L.append(H("How the applications connect"))
    L.append("Connections from one application to another (tests and documentation links excluded), then the "
             "parts of the target each one depends on: its integration surface. Parts known only from documents "
             "or still unfinished are contract risks: confirm them before building on them.\n")
    if not app_pair:
        L.append("No connections between applications in this map.\n")
    for (x, y), c in app_pair.most_common():
        L.append(f"**{name(x)} → {name(y)}**: {c} connections ({', '.join(f'{k} {v}' for k, v in app_kinds[(x, y)].most_common())}); "
                 f"{len(surface[(x, y)])} parts of {name(y)} used.\n")
        L.append(f"| Part of {name(y)} | Kind | Known from | Status | Used by |\n|---|---|---|---|---|")
        for t, users in sorted(surface[(x, y)].items(), key=lambda kv: -sum(kv[1].values()))[:15]:
            n = nodes[t]
            L.append(f"| {n['name']} | {n['kind']} | {n.get('source') or 'code'} | {n.get('status', '')} | "
                     f"{', '.join(f'{name(s)} ({k})' for s, k in users.most_common(4))} |")
        if len(surface[(x, y)]) > 15:
            L.append(f"\n… and {len(surface[(x, y)]) - 15} more parts.")
        risky = [t for t in surface[(x, y)] if nodes[t].get("source") in ("docs", "inferred")
                 or nodes[t].get("status") in ("partial", "stub", "planned", "unknown")]
        if risky:
            L.append(f"\nContract risks: {len(risky)} of these parts {'is' if len(risky) == 1 else 'are'} known only "
                     "from documents or inference, or unfinished.\n")
        else:
            L.append("")
    unmapped = [r for r in apps if nodes[r].get("status") == "unknown"]
    if unmapped:
        L.append("Not mapped yet, so their connections are missing above: " + ", ".join(name(r) for r in unmapped) + ".\n")

    # ---- integration contracts
    app_of = lambda i: chain(i)[0]
    link = lambda i: f"[{name(i)}](dist/index.html#{tok(i)})"

    def verdict(t):
        n = nodes[t]
        if n.get("source") == "inferred" and n.get("status") == "unknown":
            return "not served"
        if n.get("source") == "docs":
            return "documents only"
        if n.get("status") in ("partial", "stub", "planned"):
            return "unfinished"
        if n.get("source") == "inferred":
            return "inferred"
        return "served"
    cross = [e for e in work if app_of(e["from"]) in apps and app_of(e["to"]) in apps and app_of(e["from"]) != app_of(e["to"])]
    calls_into = defaultdict(list)
    for e in cross:
        calls_into[e["to"]].append(e)
    L.append(H("Integration contracts"))
    L.append("Every part of one application that another calls, configures or reads, checked against how the target is "
             "known. \"Not served\" means the caller names something the target's code does not declare (the mapping "
             "marks such boxes inferred, status unknown); \"documents only\" means only documents vouch for it. Both "
             "fail at run time or are skipped silently, so confirm them first.\n")
    by_verdict, risky_rows = Counter(), []
    for t, es in calls_into.items():
        v = verdict(t)
        by_verdict[v] += len(es)
        if v != "served":
            risky_rows.append((v, t, len(es), Counter(name(unit(e["from"])) for e in es), es[0].get("evidence", "")))
    order = ["not served", "documents only", "unfinished", "inferred"]
    risky_rows.sort(key=lambda r: (order.index(r[0]), -r[2], r[1]))
    if cross:
        L.append("Call sites by verdict: " + ", ".join(f"{k} {c}" for k, c in by_verdict.most_common()) + ".\n")
    if risky_rows:
        L.append("| Target | Application | Verdict | Call sites | Callers | First evidence |\n|---|---|---|---:|---|---|")
        for v, t, c, callers, ev in risky_rows[:30]:
            L.append(f"| {link(t)} | {name(app_of(t))} | {v} | {c} | {', '.join(f'{k} ({n})' for k, n in callers.most_common(3))} | `{ev}` |")
        if len(risky_rows) > 30:
            L.append(f"\n… and {len(risky_rows) - 30} more.")
    pins = [(r, p) for r in d["meta"].get("repos", []) for p in (r.get("pinned") or [])]
    if pins:
        L.append("\n**Pinned copies.** An application that vendors another at an older commit integrates against that "
                 "version, not the one mapped here:\n")
        for r, p in pins:
            L.append(f"- {name(p['by']) if p.get('by') in nodes else p.get('by')} pins {r.get('name')} as of {p.get('date', '?')}, "
                     f"{p.get('behind', '?')} commits behind the mapped commit{'. ' + p['note'] if p.get('note') else ''}.")
    shared = defaultdict(set)
    for e in cross:
        shared[e["to"]].add(app_of(e["from"]))
    multi = sorted(((t, a_) for t, a_ in shared.items() if len(a_) > 1), key=lambda ta: -len(calls_into[ta[0]]))
    if multi:
        L.append("\n**Contracts shared by several applications.** Changing one of these breaks more than one caller:\n")
        for t, a_ in multi[:15]:
            L.append(f"- {link(t)} ({name(app_of(t))}): used by {', '.join(sorted(name(x) for x in a_))}, {len(calls_into[t])} call sites")
    L.append("")

    # ---- capabilities duplicated across applications
    L.append(H("Capabilities duplicated across applications"))
    L.append("Two signals. First, applications that each make their own network calls to the same application or outside "
             "service (hosting and databases left out: every application has its own). Second, parts in different applications whose names and summaries describe the same job. Both "
             "point at a shared implementation; the second is a text match, so read both boxes before acting.\n")
    clients = defaultdict(lambda: defaultdict(Counter))
    infra = lambda x: nodes[x].get("parent") in INFRA_GROUPS or x in INFRA_SERVICES
    for e in work:
        src_app, dst = app_of(e["from"]), e["to"]
        if e["kind"] not in ("http", "calls") or src_app not in apps:
            continue
        target = app_of(dst) if app_of(dst) in apps else (dst if nodes[dst]["kind"] == "external" and not infra(dst) else None)
        if target and target != src_app:
            clients[target][src_app][unit(e["from"])] += 1
    parallel = sorted(((t, per) for t, per in clients.items() if len(per) > 1),
                      key=lambda tp: (nodes[tp[0]]["kind"] != "app", -len(tp[1]), -sum(sum(c.values()) for c in tp[1].values()), tp[0]))
    if parallel:
        L.append("**Their own client for the same target:**\n")
        for t, per in parallel[:15]:
            parts = [f"{name(a_)} through {', '.join(link(u) for u, _ in units.most_common(3))}"
                     f"{f' and {len(units) - 3} more' if len(units) > 3 else ''}" for a_, units in sorted(per.items(), key=lambda kv: name(kv[0]))]
            L.append(f"- **{name(t)}**: " + "; ".join(parts))
    cands = [i for i, n in nodes.items() if n["kind"] in ("module", "component", "service", "group")
             and app_of(i) in apps and len(chain(i)) >= 3]
    bag = {i: words(nodes[i]["name"] + " " + nodes[i].get("summary", "")) for i in cands}
    df = Counter(w for b in bag.values() for w in b)
    idf = {w: math.log(len(cands) / c) for w, c in df.items()}
    norm = {i: math.sqrt(sum(idf[w] ** 2 for w in b)) or 1.0 for i, b in bag.items()}
    by_word = defaultdict(list)
    for i, b in bag.items():
        for w in b:
            if df[w] <= 40:
                by_word[w].append(i)
    overlap = Counter()
    for w, ids_ in by_word.items():
        for x in range(len(ids_)):
            for y in range(x + 1, len(ids_)):
                if app_of(ids_[x]) != app_of(ids_[y]):
                    overlap[tuple(sorted((ids_[x], ids_[y])))] += idf[w] ** 2
    similar = sorted(((pr, sc / (norm[pr[0]] * norm[pr[1]])) for pr, sc in overlap.items()), key=lambda ps: (-round(ps[1], 6), ps[0]))
    similar = [ps for ps in similar if ps[1] >= 0.35]
    if similar:
        L.append("\n**Similar parts in different applications** (text similarity of name and summary):\n")
        L.append("| Part | Application | Part | Application | Similarity |\n|---|---|---|---|---:|")
        for (i, j), sc in similar[:15]:
            L.append(f"| {link(i)} | {name(app_of(i))} | {link(j)} | {name(app_of(j))} | {sc:.2f} |")
    if not parallel and not similar:
        L.append("None found.")
    L.append("")

    # ---- engagements: actions filed by process step and tagged with capabilities
    steps = d["meta"].get("process") or []
    actions = [i for i, n in nodes.items() if n.get("phase") and n["kind"] != "group"]
    # capabilities that mostly live in these steps are tooling one shared component could serve;
    # the rest (analysis, delivery, intake) are practices each engagement naturally repeats
    TOOLING_STEPS = {"sources", "context", "dashboard", "mapping", "buildout", "reuse"}
    cap_steps = defaultdict(Counter)
    engs = sorted({at_depth(i, 1) for i in actions}, key=name)
    cap_by_eng, cap_examples = defaultdict(Counter), defaultdict(list)
    gaps, shared_caps = [], []
    if steps and actions:
        step_name = {p["id"]: p["name"] for p in steps}
        L.append(H("The process, engagement by engagement"))
        L.append("Actions filed under each step of the unified process. A step with no actions is work that engagement "
                 "has not done (or not recorded): either a gap to fill or a step that did not apply.\n")
        L.append("| Step | " + " | ".join(name(e) for e in engs) + " |\n|---|" + "---:|" * len(engs))
        count = Counter((nodes[i]["phase"], at_depth(i, 1)) for i in actions)
        for p in steps:
            L.append(f"| {p['name']} | " + " | ".join(str(count[(p['id'], e)]) if count[(p['id'], e)] else "none" for e in engs) + " |")
        dated = defaultdict(list)
        for i in actions:
            if nodes[i].get("date"):
                dated[at_depth(i, 1)].append(nodes[i]["date"])
        if dated:
            L.append("\nTime span of the recorded actions: " + "; ".join(
                f"{name(e)} {min(dated[e])} to {max(dated[e])}" for e in engs if dated[e]) + ".\n")
        for i in actions:
            for c in nodes[i].get("capabilities") or []:
                cap_by_eng[c][at_depth(i, 1)] += 1
                cap_examples[(c, at_depth(i, 1))].append(i)
                cap_steps[c][nodes[i]["phase"]] += 1
        tooling = lambda c: cap_steps[c].most_common(1)[0][0] in TOOLING_STEPS
        L.append(H("Capabilities across engagements: new features and shared work"))
        L.append("Each action carries capability tags. A capability some engagements have and others lack is a "
                 "candidate new feature for the ones without it, with a working example to start from. A capability "
                 "every engagement built on its own is a candidate for one shared component in the process.\n")
        for c in sorted(cap_by_eng, key=lambda c: (-len(cap_by_eng[c]), -sum(cap_by_eng[c].values()), c)):
            have = [e for e in engs if cap_by_eng[c][e]]
            lack = [e for e in engs if not cap_by_eng[c][e]]
            if lack and have:
                gaps.append((c, have, lack))
            elif len(have) > 1 and tooling(c):
                shared_caps.append((c, have))
        shared_caps.sort(key=lambda ch: (-sum(cap_by_eng[ch[0]].values()), ch[0]))
        if gaps:
            L.append("**Some have it, some do not** (most widely held first):\n")
            L.append("| Capability | Kind | Has it | Lacks it | Start from |\n|---|---|---|---|---|")
            for c, have, lack in gaps[:30]:
                ex = cap_examples[(c, have[0])][0]
                L.append(f"| {c} | {'tooling' if tooling(c) else 'practice'} | {', '.join(name(e) for e in have)} | "
                         f"{', '.join(name(e) for e in lack)} | {link(ex)} |")
            if len(gaps) > 30:
                L.append(f"\n… and {len(gaps) - 30} more.")
        if shared_caps:
            L.append("\n**Tooling every engagement built on its own** (candidates for one shared component; practices such "
                     "as analyses and syncs are left out because each engagement repeats them by nature):\n")
            for c, have in shared_caps[:20]:
                L.append(f"- {c}: " + "; ".join(f"{name(e)} ({pl(cap_by_eng[c][e], 'action')}, e.g. {link(cap_examples[(c, e)][0])})" for e in have))
        L.append("\n" + H("Connections between engagements"))
        eng_of = lambda i: at_depth(i, 1) if chain(i)[0] == chain(actions[0])[0] else None
        carried = [(e_["from"], e_["to"]) for e_ in edges if eng_of(e_["from"]) and eng_of(e_["to"]) and eng_of(e_["from"]) != eng_of(e_["to"])]
        if carried:
            L.append("**Carried from one engagement to another:**\n")
            for a_, b_ in carried[:20]:
                L.append(f"- {name(eng_of(a_))} → {name(eng_of(b_))}: {link(a_)} → {link(b_)}")
        used = defaultdict(set)
        for e_ in edges:
            for here, there in ((e_["from"], e_["to"]), (e_["to"], e_["from"])):
                if eng_of(here) and not eng_of(there):
                    used[unit(there)].add(eng_of(here))
        common = sorted(((t, es) for t, es in used.items() if len(es) > 1), key=lambda te: (-len(te[1]), name(te[0])))
        if common:
            L.append("\n**Systems, sources and agents more than one engagement uses:**\n")
            for t, es in common[:25]:
                L.append(f"- {link(t)} ({name(chain(t)[0])}): {', '.join(sorted(name(e) for e in es))}")
        if not carried and not common:
            L.append("None recorded yet.")
        L.append("")

    # ---- coupling between subsystems
    pair, kinds = Counter(), defaultdict(Counter)
    for e in work:
        a_, b_ = at_depth(e["from"], 1), at_depth(e["to"], 1)
        if a_ != b_:
            pair[(a_, b_)] += 1
            kinds[(a_, b_)][e["kind"]] += 1
    L.append(H("Coupling between subsystems"))
    L.append("Connections from one subsystem to another (tests and documentation links excluded). "
             "Two-way pairs depend on each other, which makes them harder to change or deploy separately.\n")
    L.append("| From | To | Connections | Kinds | Two-way |\n|---|---|---:|---|---|")
    for (x, y), c in pair.most_common(25):
        back = pair.get((y, x), 0)
        L.append(f"| {name(x)} | {name(y)} | {c} | {', '.join(f'{k} {v}' for k, v in kinds[(x, y)].most_common(3))} | "
                 f"{'yes (' + str(back) + ' back)' if back else ''} |")

    # ---- hubs
    fan_in, fan_out = Counter(), Counter()
    for e in work:
        ua, ub = unit(e["from"]), unit(e["to"])
        if ua != ub and nodes[ub]["kind"] != "external":
            fan_in[ub] += 1
        if ua != ub and nodes[ua]["kind"] != "external":
            fan_out[ua] += 1
    L.append(chr(10) + H("Hubs"))
    L.append("Module-level boxes with the most incoming connections (most depended on: changes here ripple) "
             "and outgoing connections (depend on the most: hardest to test in isolation).\n")
    L.append("| Most depended on | In | | Depends on the most | Out |\n|---|---:|---|---|---:|")
    fi, fo = fan_in.most_common(15), fan_out.most_common(15)
    for k in range(15):
        left = f"{name(fi[k][0])} | {fi[k][1]}" if k < len(fi) else " | "
        right = f"{name(fo[k][0])} | {fo[k][1]}" if k < len(fo) else " | "
        L.append(f"| {left} | | {right} |")

    # ---- outside services
    ext_users = defaultdict(Counter)
    for e in work:
        for here, there in ((e["from"], e["to"]), (e["to"], e["from"])):
            if nodes[there]["kind"] == "external" and nodes[here]["kind"] != "external":
                ext_users[there][at_depth(here, 1)] += 1
    L.append(chr(10) + H("Outside services"))
    L.append("Which subsystems touch each service. A service many subsystems rely on is a single point of "
             "failure worth isolating behind one adapter.\n")
    L.append("| Service | Connections | Subsystems using it |\n|---|---:|---|")
    for x, users in sorted(ext_users.items(), key=lambda kv: -sum(kv[1].values())):
        L.append(f"| {name(x)} | {sum(users.values())} | {', '.join(f'{name(s)} ({c})' for s, c in users.most_common(6))} |")

    # ---- delivery status
    L.append(chr(10) + H("Delivery status by subsystem"))
    L.append("Status labels recorded while mapping (only where there was evidence). Partial, stub and planned "
             "parts are where build-out work sits.\n")
    L.append("| Subsystem | " + " | ".join(STATUS_ORDER[:5]) + " |\n|---|" + "---:|" * 5)
    for s in sorted(subs, key=lambda i: -len(desc(i))):
        st = Counter(nodes[x].get("status") for x in desc(s) if nodes[x].get("status"))
        if st:
            L.append(f"| {name(s)} | " + " | ".join(str(st.get(k, "")) for k in STATUS_ORDER[:5]) + " |")

    # ---- tests
    tested = set()
    for e in edges:
        if e["kind"] == "tests":
            for x in chain(e["to"]):
                tested.add(x)
    L.append(chr(10) + H("Test coverage (from test-to-code connections)"))
    L.append("Modules with at least one test file pointing at them or at something inside them. A proxy, "
             "not line coverage.\n")
    L.append("| Subsystem | Modules | With tests | Untested hubs |\n|---|---:|---:|---|")
    hub_set = {x for x, _ in fan_in.most_common(60)}
    for s in sorted(subs, key=lambda i: -len(desc(i))):
        mods = [x for x in desc(s) if nodes[x]["kind"] in ("module", "component") and x != s]
        if not mods:
            continue
        with_t = [x for x in mods if x in tested]
        untested_hubs = [name(x) for x in mods if x not in tested and x in hub_set][:5]
        L.append(f"| {name(s)} | {len(mods)} | {len(with_t)} | {', '.join(untested_hubs)} |")

    # ---- knowledge gaps
    L.append(chr(10) + H("Knowledge gaps"))
    for r in roots:
        dd = desc(r)
        docs = sum(1 for x in dd if nodes[x].get("source") == "docs")
        inf = sum(1 for x in dd if nodes[x].get("source") == "inferred")
        prov = nodes[r].get("provenance", "")
        L.append(f"- **{name(r)}**: {len(dd) - 1} boxes; {docs} known only from documents, {inf} inferred. {prov}")

    # ---- findings
    found = []
    for i, n in nodes.items():
        for text in [n.get("detail", "")] + list(n.get("facts", []) or []):
            for m in FINDING.finditer(text or ""):
                s = m.group(0).strip()
                if 25 < len(s) < 260:
                    found.append((at_depth(i, 1), n["name"], s))
                    break
    L.append("\n" + H(f"Findings recorded while mapping ({len(found)})"))
    L.append("Sentences in the map that describe gaps, drift between documents and code, or likely defects. "
             "Picked by keyword, so some are benign; verify before acting.\n")
    by_sub = defaultdict(list)
    for s, nm, text in found:
        by_sub[s].append((nm, text))
    for s, items in sorted(by_sub.items(), key=lambda kv: -len(kv[1])):
        L.append(f"\n**{name(s)}** ({len(items)})\n")
        for nm, text in items[:12]:
            L.append(f"- *{nm}*: {text}")
        if len(items) > 12:
            L.append(f"- … and {len(items) - 12} more")

    # ---- build-out candidates
    inbound = Counter()
    for e in work:
        for x in chain(e["to"]):
            inbound[x] += 1
    unfinished = [(i, inbound[i]) for i, n in nodes.items() if n.get("status") in ("partial", "stub", "planned")]
    unfinished.sort(key=lambda t: (-t[1], t[0]))
    L.append(chr(10) + H("Build-out candidates"))
    L.append("Ranked by how much of the system leans on them. These are prompts for a review, not decisions; "
             "`BUILDOUT.md` turns them, with the contract and duplication findings above, into a draft plan.\n")
    L.append("**Unfinished parts with the most dependents** (partial, stub or planned):\n")
    for i, c in unfinished[:15]:
        L.append(f"- {name(i)} ({nodes[i]['status']}, {c} incoming): {nodes[i].get('summary', '')}")
    in_app = lambda i: nodes[chain(i)[0]]["kind"] == "app"
    two_way = sorted({tuple(sorted(p)) for p in pair if (p[1], p[0]) in pair and in_app(p[0]) and in_app(p[1])},
                     key=lambda p: (-(pair[p] + pair[(p[1], p[0])]), p))
    if two_way:
        L.append("\n**Two-way dependencies between subsystems** (candidates for a clearer interface):\n")
        for x, y in two_way[:10]:
            L.append(f"- {name(x)} ↔ {name(y)}: {pair[(x, y)]} one way, {pair[(y, x)]} back")
    untested = [(x, c) for x, c in fan_in.most_common(40) if x not in tested and nodes[x]["kind"] in ("module", "component", "service")]
    if untested:
        L.append("\n**Heavily used modules with no test pointing at them:**\n")
        for x, c in untested[:10]:
            L.append(f"- {name(x)} ({c} incoming)")

    # ---- draft build-out plan: the method's phase 6 format, ranked by leverage over effort
    def files_of(ids_):
        return {p.split(":")[0] for i in ids_ for x in desc(i) for p in (nodes[x].get("paths") or [])}

    def effort(ids_, floor=0):
        n = max(len(files_of(ids_)), floor)
        return (("S", 1, "a day or two") if n <= 3 else ("M", 2, "about a week") if n <= 12 else ("L", 4, "two weeks or more")) + (n,)
    items = []

    def item(key, title, problem, evidence, change, impact, impact_text, ids_, after=(), floor=0):
        e = effort(ids_, floor)
        items.append(dict(key=key, title=title, problem=problem, evidence=evidence, change=change, impact=impact,
                          impact_text=impact_text, effort=e, score=impact / e[1], after=list(after)))
    broken = defaultdict(list)
    for v, t, c, callers, ev in risky_rows:
        # a defect is a call that cannot be answered; documents one application wrote about another are not calls
        if v == "not served" or (v == "documents only" and any(e["kind"] in ("http", "calls") for e in calls_into[t])):
            for sa in {app_of(e["from"]) for e in calls_into[t] if e["kind"] in ("http", "calls", "configures")}:
                broken[(sa, app_of(t))].append((v, t, sum(1 for e in calls_into[t] if app_of(e["from"]) == sa), ev))
    for (sa, ta), rows in broken.items():
        sites = sum(r[2] for r in rows)
        callers = {unit(e["from"]) for _, t, _, _ in rows for e in calls_into[t] if app_of(e["from"]) == sa}
        n_unserved = sum(1 for r in rows if r[0] == "not served")
        how = (f"that {name(ta)}'s code does not declare" if n_unserved == len(rows) else "known only from documents" if not n_unserved
               else f"{n_unserved} of them not declared in {name(ta)}'s code and the rest known only from documents")
        item(("contract", ta, sa), f"Fix what {name(sa)} expects from {name(ta)}",
             f"{pl(sites, 'call site')} in {name(sa)} {'depends' if sites == 1 else 'depend'} on {pl(len(rows), 'part')} of {name(ta)} {how}. "
             "Calls like these fail at run time or are skipped silently.",
             [f"{link(t)} ({v}): {pl(c, 'call site')}, first at `{ev}`" for v, t, c, ev in sorted(rows, key=lambda r: -r[2])[:8]],
             f"Point each caller at what {name(ta)} serves today, or add what is missing to {name(ta)}, and make a failed call "
             "visible (an error or an alert) instead of a quiet skip.", sites * 3, pl(sites, "call site"), list(callers) + [r[1] for r in rows])
    for r, p in pins:
        sites = sum(1 for e in cross if app_of(e["from"]) == p.get("by") and app_of(e["to"]) == r.get("key"))
        item(("pin", r.get("key")), f"Bring {name(p['by']) if p.get('by') in nodes else p.get('by')}'s copy of {r.get('name')} up to date",
             f"It vendors {r.get('name')} as of {p.get('date', '?')}, {p.get('behind', '?')} commits behind the version mapped here, "
             "so its integration is built and tested against an old version.",
             [f"{link(p['by'])}: pin at {p.get('path', '')}" if p.get("by") in nodes else str(p)],
             "Move the pin to a current release on a schedule, or stop vendoring and depend on the deployed service's API with a version check.",
             max(sites, 1), f"{sites} cross-application call sites", [p.get("by")] if p.get("by") in nodes else [], after=[("contract", r.get("key"), p.get("by"))])
    for t, per in parallel:
        sites = sum(sum(c.values()) for c in per.values())
        if nodes[t]["kind"] != "app" and sites < 12:
            continue
        units = [u for c in per.values() for u in c]
        item(("client", t), f"One shared client for {name(t)}",
             f"{len(per)} applications call {name(t)} through their own code ({len(units)} modules), so authentication, "
             "retries, timeouts and failure handling drift apart.",
             [f"{name(a_)}: " + ", ".join(link(u) for u, _ in c.most_common(4)) for a_, c in sorted(per.items(), key=lambda kv: name(kv[0]))],
             f"Extract one small client package for {name(t)} that holds those rules in one place, and move each application onto it.",
             sites, f"{sites} call sites in {len(per)} applications", units, after=[("contract", t)])
    for i, c in unfinished[:6]:
        item(("unfinished", i), f"Finish or retire {name(i)}", f"It is {nodes[i]['status']}, yet {c} connections lead into it.",
             [f"{link(i)}: {nodes[i].get('summary', '')}"],
             "Decide whether it stays. If it does, finish the missing parts its details name; if not, remove what depends on it.",
             c, f"{c} incoming connections", [i], floor=4)
    for x, y in two_way[:3]:
        n_ = pair[(x, y)] + pair[(y, x)]
        item(("coupling", x, y), f"Untangle {name(x)} and {name(y)}",
             f"They depend on each other ({pair[(x, y)]} connections one way, {pair[(y, x)]} back), so neither can change or ship alone.",
             [link(x), link(y)], "Keep the direction that should remain and put the other behind a narrow interface: events, a client or a shared contract.",
             n_, f"{n_} connections", [x, y])
    if untested:
        top = untested[:6]
        item(("tests",), "Test the most depended-on modules", f"{len(top)} heavily used modules have no test pointing at them.",
             [f"{link(x)}: {c} incoming" for x, c in top], "Add contract tests at each module's public interface first, then cover the paths the guided flows walk.",
             sum(c for _, c in top), f"{sum(c for _, c in top)} incoming connections", [x for x, _ in top])
    per_app = defaultdict(Counter)
    for e in work:
        for here, there in ((e["from"], e["to"]), (e["to"], e["from"])):
            if nodes[there]["kind"] == "external" and not infra(there) and nodes[here]["kind"] != "external" and app_of(here) in apps:
                per_app[(app_of(here), there)][at_depth(here, 1)] += 1
    shared_clients = {it["key"][1] for it in items if it["key"][0] == "client"}
    for (ap, x), users in sorted(per_app.items(), key=lambda kv: (-len(kv[1]), -sum(kv[1].values()), kv[0]))[:4]:
        if len(users) < 3 or x in shared_clients:
            continue
        callers = {unit(e["from"]) for e in work if e["to"] == x and app_of(e["from"]) == ap}
        item(("adapter", ap, x), f"Put {name(x)} behind one adapter in {name(ap)}",
             f"{len(users)} subsystems of {name(ap)} talk to {name(x)} directly, so an outage, a price change or an API change touches all of them.",
             [f"{name(s_)}: {c} connections" for s_, c in users.most_common(6)],
             "Route every call through one adapter, with timeouts, retries and a switch to a fallback.",
             sum(users.values()), f"{sum(users.values())} connections from {len(users)} subsystems", list(callers))
    for c, have, lack in sorted(gaps, key=lambda g: (not tooling(g[0]), -len(g[1]), -sum(cap_by_eng[g[0]].values()), g[0]))[:8]:
        ex = [cap_examples[(c, e)][0] for e in have]
        n_ = sum(cap_by_eng[c][e] for e in have)
        item(("feature", c), f"Bring {c} to {', '.join(name(e) for e in lack)}",
             f"{', '.join(name(e) for e in have)} {'has' if len(have) == 1 else 'have'} {c} ({pl(n_, 'action')}); "
             f"{', '.join(name(e) for e in lack)} {'does' if len(lack) == 1 else 'do'} not.",
             [f"{name(e)}: {link(cap_examples[(c, e)][0])}" for e in have],
             "Start from the working example, adapt it to the engagement's sources, and record it in the process so the next engagement starts with it.",
             len(have) * 10 + n_, f"{len(have)} of {len(engs)} engagements already do it", ex)
    for c, have in shared_caps[:4]:
        n_ = sum(cap_by_eng[c][e] for e in have)
        item(("standard", c), f"Make {c} one shared component",
             f"All {len(have)} engagements built {c} on their own ({pl(n_, 'action')}), so each copy drifts.",
             [f"{name(e)}: {link(cap_examples[(c, e)][0])}" for e in have],
             "Extract the best version into shared tooling, point each engagement at it, and make it a default step of the process.",
             n_ * 2, f"{pl(n_, 'action')} across {len(have)} engagements", [cap_examples[(c, e)][0] for e in have])
    first = sorted((it for it in items if it["key"][0] == "contract"), key=lambda it: (-it["impact"], it["title"]))
    across = sorted((it for it in items if it["key"][0] in ("feature", "standard")), key=lambda it: (-it["score"], it["title"]))[:10]
    inside = sorted((it for it in items if it["key"][0] not in ("contract", "feature", "standard")), key=lambda it: (-it["score"], it["title"]))[:12]
    items = first + across + inside
    heading = {id(it): "Fix first" for it in first}
    heading.update({id(it): "Across engagements: new features and shared components" for it in across})
    heading.update({id(it): "Inside the applications" for it in inside})
    titles = {it["key"]: (k + 1, it["title"]) for k, it in enumerate(items)}
    P = [f"# Draft build-out plan: {d['meta'].get('title', 'Topo map')}\n",
         f"Generated by `pipeline/analyze.py` from the map ({len(nodes):,} boxes). Items are ranked by leverage (how much of "
         "the system each one touches) over a rough effort estimate from the number of files behind its evidence. Every "
         "item is a proposal to check against the code with the owner, not a decision. Links open the map at the evidence; "
         "the numbers behind each item are in `ANALYSIS.md`." + (
             (" Item 1 is a call that fails today; it comes first because it is a defect, not a trade-off." if len(first) == 1 else
              f" Items 1 {'and' if len(first) == 2 else 'to'} {len(first)} are calls that fail today; they come first because they "
              "are defects, not trade-offs.") if first else "") + "\n"]
    last = None
    for k, it in enumerate(items, 1):
        size, _, span, nfiles = it["effort"]
        if across and heading[id(it)] != last:  # sections only when engagements add their own block
            last = heading[id(it)]
            P.append(f"# {last}\n")
        P.append(f"## {k}. {it['title']}\n")
        P.append(f"**Problem.** {it['problem']}\n")
        P.append("**Evidence.**\n\n" + "\n".join(f"- {x}" for x in it["evidence"]) + "\n")
        P.append(f"**Proposed change.** {it['change']}\n")
        P.append(f"**Impact.** {it['impact_text']}.\n")
        P.append(f"**Effort.** {size}, {span} ({pl(nfiles, 'file')} behind the evidence; a heuristic).\n")
        # an "after" key names every item it prefixes: ("contract", t) is each fix of calls into t
        deps = sorted({titles[key] for a_ in it["after"] for key in titles if key[:len(a_)] == tuple(a_) and titles[key][0] != k})
        P.append("**Dependencies.** " + ("; ".join(f"after item {n} ({t})" for n, t in deps) if deps else "none found in the map") + ".\n")
    plan_out = os.path.join(os.path.dirname(a.out) if a.out else a.map_dir, "BUILDOUT.md")
    open(plan_out, "w").write("\n".join(P))

    out = a.out or os.path.join(a.map_dir, "ANALYSIS.md")
    open(out, "w").write("\n".join(L) + "\n")
    print(f"wrote {out}: {len(pair)} subsystem pairs, {len(found)} findings, {len(unfinished)} unfinished parts; "
          f"{plan_out}: {len(items)} draft items")


if __name__ == "__main__":
    main()
