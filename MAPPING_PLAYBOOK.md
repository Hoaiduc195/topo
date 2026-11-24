# Mapping playbook

How to chart a set of codebases into a Topo map. The example in `maps/saleor/` was produced this
way: eleven mapping agents in parallel, about 30 minutes of wall-clock time, 2,120 boxes and 2,763
connections, every cited line checked.

The method's rule of thumb: **agents read code and write structured claims with evidence; scripts
check every claim they can; a person decides what is shared.**

---

## 1. Get the code locally

Clone every repository you want on the map. Anything you can't read can still appear, but only as
"seen from" another app (dashed outlines, `"source": "docs"`) or as an empty, labelled region.

Orient yourself before splitting the work: top-level docs, folder tree, file counts per folder,
entry points, and any existing architecture or inventory documents. Those documents are good
starting points for the agents, but the code is the source of truth.

**Several repositories in one map.** Every path in a map is relative to one checkout, and file ids
are `f:<path>`, so two repositories would collide. Build one combined, read-only checkout from
snapshots, one folder per repository, each at the commit you map:

```
mkdir -p /tmp/checkout/<repo-b> /tmp/checkout/<repo-c>
git -C ~/<repo-a> archive <commit> | tar -x -C /tmp/checkout          # the main application at the root
git -C ~/<repo-b> archive <commit> | tar -x -C /tmp/checkout/<repo-b>
git -C ~/<repo-c> archive <commit> | tar -x -C /tmp/checkout/<repo-c>
```

For a new map, `python3 -I pipeline/init.py <repo> [<repo> ...] [--name <name>]` does all of this in
one step. It takes local clones or git URLs and writes the map folder (`~/topo-maps/<name>/` by
default, outside this repository): `topo.config.json` with every repository at its HEAD commit,
`skeleton.json` with one box per application and the outside-services region, `clones.json` (where
each repository is cloned on this machine), the read-only `checkout/`, and `ORIENT.md`, which lists
each repository's languages, largest folders, manifests and entry points and suggests how many agents
the code needs. After that, `python3 -I pipeline/checkout.py <map> --out <folder>` rebuilds a checkout
from the config and `clones.json`. `git archive` reads committed files only, so uncommitted work in a
clone never reaches the map and the clone is not touched. Agents then cite `<repo-b>/src/...`, and the config's `repos` entry for
that application carries `"prefix": "<repo-b>/"` so links into the code drop the folder. Extract the
route lists of every server first (`pipeline/routes.py`) (method, full path, file and line) and hand them to every agent,
so endpoints declared by one area and called from another or from another application get the same
ids.

## 2. Draw the skeleton

`init.py` starts `skeleton.json` with one box per application and the outside-services region; draw
the rest by hand (a short script that writes it is fine):

- one `app:<slug>` node per application or repository, `kind: "app"`, no parent;
- one region for outside systems (`kind: "group"`), with sub-groups (data, AI providers,
  collaboration, hosting, the product's own clients, people) and one `x:<slug>` node per service;
- level-1 subsystems under each app;
- level-2 groups only where several agents will share a subsystem, so they agree on parents.

Then `topo.config.json` (`init.py` fills in the title, regions and repositories): the title, a
rectangle and hue per region (world units; the example uses a 2600 × 1420 world with three
applications side by side and outside services along the bottom),
the `owners` list (path prefix → group, used when a reference has no exact node; first match wins,
so put specific prefixes before general ones), `endpoint_fallback` (the endpoint service names
agents may use), `prefix_fallback` for other id families, and a short provenance line per app.
Each `repos` entry has a `url`, the repository's web address, for links into the code at its `commit`.
GitHub, GitLab and Bitbucket shape those links differently: `init.py` sets `host` (`gitlab` or
`bitbucket`; GitHub needs none) from the remote, and a GitLab server under another name needs `"host":
"gitlab"` by hand. A repository on any other host gets no `url` and its files show without links.
Each entry may also carry a `prefix` (see above) and a `pinned` list, one entry per application
that vendors this repository at an older commit (`by`, `commit`, `date`, `behind`, `path`);
`analyze.py` reports those pins as integration risks.

A region can be a strip instead of nested boxes: give it a `strip` with `columns` (`id`, `name` and an
optional `short` name, one per column) and, optionally, `lanes` (lane id to the region whose colors it
takes). Its children become lanes, one row each, and their children marks, placed in the column whose
`id` is the mark's `date`; a mark's `facts` show when you hover it. A timeline of a week's work, one lane per team, is one.

Anything mechanical can be generated instead of mapped by an agent. In the example, the agent
library (one box per role prompt, one group per team) came from a short script over the platform's
team manifest and the prompts' frontmatter.

## 3. Split into areas

One area per agent, typically 100 to 300 boxes each. For every area decide:

- the files it owns (by path), so no file gets two nodes;
- its group-id prefixes (`core.`, `web.` …) and the skeleton parents it attaches to;
- a node budget and a "must cover" list (entry points, core mechanisms, data stores, external
  calls, the 2 to 3 flows that explain the area).

## 4. Brief the agents (in parallel)

`python3 -I pipeline/brief.py areas.json` writes this brief for every area from one areas file (owned
paths, parents, prefixes, budget, must-cover, flows), checks that no file is owned twice and lists files
nobody owns. The template it fills in is below. Agents read `pipeline/SCHEMA.md` and the skeleton first, write
their slice where their brief says (the areas file's slices folder), and run the validator against
the checkout until it prints OK. The merge step copies the slices into the map's `parts/`.

```text
You are mapping one slice of a codebase for an interactive, zoomable architecture map.

FIRST read <map>/../../pipeline/SCHEMA.md and <map>/skeleton.json completely.
Repo: <checkout path> (read-only: never modify, commit or push). Orientation docs: <list>.
The code is the source of truth.

## Your area: `<area>`
Output: <slices>/<area>.json (split into <area>.1.json, <area>.2.json if large).
Group-id prefixes: <prefixes>. Parents you attach to: <skeleton ids>. Node budget: <n>.

Files you OWN: <paths>.
Other areas own (reference by predictable id, don't create): <paths and their areas>.

## Must cover
1. <entry points, with every route as an endpoint node>
2. <core mechanisms, at symbol level, with 10 to 15 verbatim code excerpts>
3. <data stores and the reads/writes into them>
4. <calls to other areas and to external services x:...>
5. Flows (2 to 3): <titles>

Before finishing: re-open the files behind your 10 most important nodes and check every claim.
Run: python3 -I pipeline/validate.py <map> --repo <checkout> <your part files>   until OK.

Final reply (at most 150 words): counts, part files, notable cross-area references, anything
you were unsure about. Do not paste the JSON.
```

Validating one slice on its own accepts references to other areas' files (`f:`, `d:`, `ep:`) but not
to their group ids, which it cannot see yet; agents point at a file or folder instead, and the merge
step retargets those references to the groups.

Agents also report bugs and doc-versus-code mismatches they notice. Verify those before passing
them on; they are often the most valuable by-product of a mapping.

## 5. Merge and check

```
python3 -I pipeline/finish.py maps/<name> --merge   # copy the slices into parts/, then every check below
```

`finish.py` runs, in one step, what this section describes: `validate.py` on every slice together
against the checkout, `refs.py`, `build.py` (merge and page), `symcheck.py` (cited lines match their
symbols, 98% or more), `depthcheck.py` (the public classes, functions, types and methods have boxes, each area has enough
symbol boxes, every symbol box cites its line and has a connection, and there are enough code excerpts) and `analyze.py`. Each tool also runs on its own. A slice already in `parts/` is
kept as it is, since this step edits those copies; run `finish.py` again after each round of edits.

`build.py` prints how references resolved. Exact matches should dominate; read the fallbacks
(a symbol resolved to its file is fine, an endpoint resolved to an unrelated node is not).
`python3 -I pipeline/refs.py <map>` lists every reference with no exact box, by slice: give routes
no server declares their own inferred box (they become contract findings), retarget references to
other areas' groups, and move flow steps onto real boxes.

## 6. Write the featured flows

Cross-area journeys are the part no single agent can write. Put them in `flows.json` with real
ids, and check every sentence against the code or the nodes' own details: these are what
newcomers read first. List the best 3 to 5 under `"feature"`.

## 7. Test, then publish

```
node test/smoke.cjs maps/<name>/dist/index.html out/   # console errors + screenshots
sh test/run.sh                                         # every check at once
```

Look at the overview, one subsystem, one deep code card, a selection and a running flow, in light
and dark and at phone width. The page is a single HTML file: open it locally, host it anywhere
static, or publish it as a Claude artifact.

## 8. Anonymize before sharing

Maps of client systems stay private. Keep everything that names the client or quotes its
figures in a private folder outside this repository. Each machine says where it is, and every tool
reads the same setting: `$TOPO_PRIVATE`, else `"private"` in `~/.config/topo/config.json`, else
`~/.topo/private` (`python3 -I pipeline/settings.py` prints it). Below, `<private>` stands for that
folder. On a machine that keeps private maps, also set `"require_rules": true` in the config file: the
leak guard then fails when it cannot find the name rules, instead of skipping the name check.

```json
{"private": "~/path/to/your/private/folder", "require_rules": true}
```

The folder:

```
<private>/
  rules.json                 real name -> stand-in rules, plus the leak-scan list (a map's own
                             rules can go in <map>/rules.json; the leak guard reads both)
  <map>/                     the named sources: skeleton.json, parts/, flows.json, topo.config.json
    generalized.json         the reviewed figures overlay (quotes the original text)
    worklist.json            fields to review (quotes the original text)
```

The shareable copy in `maps/<map>` is always regenerated from there, never edited by hand:

```
# names: mechanical, from the private rules; fails if any listed name survives
python3 -I pipeline/anonymize.py --rules <private>/rules.json \
  --src <private>/<map> --out maps/<map>
# figures: judgment, so a reviewed overlay is re-applied after every anonymize run
python3 -I pipeline/generalize.py scan maps/<map> --out <private>/<map>/worklist.json   # first time
python3 -I pipeline/generalize.py apply maps/<map> --overlay <private>/<map>/generalized.json
python3 -I pipeline/validate.py maps/<map>      # rewrites must respect the field limits
python3 -I pipeline/build.py maps/<map>
python3 -I pipeline/analyze.py maps/<map>
# leak guard: everything git would commit, names matched also inside identifiers
python3 -I pipeline/leakscan.py
```

The rules replace product, company, people, host and project names with neutral stand-ins while
tooling and service names stay. A reviewer (a person or an agent working
through the worklist) returns `{key: new text}` for the fields that state users, revenue, prices,
conversion or retention, turning them into qualitative statements and leaving technical numbers
(timeouts, ports, model parameters, design thresholds, public list prices) alone; merge the answers
into `generalized.json`. The first `apply` pins each entry to the text it replaces, so if the
private source changes later, `apply` lists the entry as stale and exits non-zero instead of
overwriting the new text. `check` (run by `apply`) prints sentences that still look like figures:
read them all. Repo links are switched off in shared copies. Never commit the rules, the worklist
or the overlay: the first undoes the anonymization and the other two quote the original figures.

## 9. Keep it current

A map is a snapshot of each repository at its mapped commit. `python3 -I pipeline/drift.py <map>`
diffs every mapped commit against the clone's head and lists the boxes whose cited lines changed,
moved or deleted files, and new folders no box covers, grouped by area, so only those areas' agents
run again (the `refresh` skill walks through it). Then set each repository's `commit` in the
private config to the head you mapped. Read the integration-contracts section of the new analysis: a
refresh is when a broken contract shows up.

To run this on a schedule, keep a fetch-only mirror of each repository (never the working clones) and
run `drift.py` against the mirrors weekly; the report opens with the areas to re-map.

## 10. Check the contracts between systems

A map shows a broken contract once it is refreshed; `pipeline/contracts.py` catches it on every
build instead. A contracts file names each target (a repository at a commit; its served routes come
from `routes.py` or an OpenAPI JSON file) and its callers (repositories, with the names or patterns of
the target's base web address, its URL, that mark a call to it). The check reports every route a caller uses that the
target does not serve, or serves only with other methods. A caller that pins the target, as a git
submodule or a vendored copy, is also checked against the routes at the pinned commit, and the
report says how many commits the pin is behind. It exits 1 when a check fails.

```
python3 -I pipeline/contracts.py <private>/contracts.json --out contracts.json
```

- **Private.** Contracts that name a client's repository live in `<private>/contracts.json`.
  Run the check wherever you run your scheduled checks; it exits 1 when a contract breaks.
- **Read-only.** Every repository is read from `git archive` of the commit, never from its working
  tree; point `repo` at a clone or at a drift-watch mirror in `<private>/mirrors/`.
- **Known failures.** A failure already reported to its owner goes in the caller's `known` list with
  where it was reported. It is still printed, marked known, but no longer fails the build; once it is
  fixed, the entry itself fails the build until it is removed, so the list only shrinks.
  `--strict` fails on known failures too.
- **What it reads.** f-strings and template literals that interpolate a base name, concatenations,
  `urljoin`, requests on a client built with the base, `curl` in shell scripts, and literal URLs
  that match a pattern. Names assigned from a base are followed in the same file. A URL built in
  another file and passed in is not followed, and it does not check credentials: a served route
  called without the key it needs passes. Read the call list it prints when you add a caller.
