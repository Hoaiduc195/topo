---
name: refresh
description: Bring a Topo map up to date with what changed in its repositories since they were mapped, re-running only the affected agent areas. Use when asked to refresh, update or re-map a map, or when a scheduled drift check reports changes.
---

# Refresh a map from drift

`<topo>` below is the folder Topo is installed in, the one that holds `pipeline/`. In Claude Code it is
`${CLAUDE_PLUGIN_ROOT}`. If that still reads as a placeholder rather than a folder (in Codex, a clone of
Topo or any other tool), `<topo>` is three folders above this file, which sits at
`<topo>/.claude/skills/<skill>/SKILL.md`. Every command below runs from any folder.

`<map>` is the map's folder: `~/topo-maps/<name>/` for a map made with the `map` skill, or
`<private>/<map>/` for a client's map (`python3 -I <topo>/pipeline/settings.py` prints `<private>`, the
private folder). If the user names no map, list the folders in `~/topo-maps/` and ask. Its
`clones.json` lists each clone.

0. **Bring the clones up to date.** Clones that `init.py` made from a URL live in `<map>/clones/`:
   `git -C <clone> pull --ff-only`. Never pull, switch or change the user's own clones; ask them to.
1. **Measure.** `python3 -I <topo>/pipeline/drift.py <map> --out <map>/drift.json`. Per repository:
   commits since the mapped one, boxes whose cited lines changed (re-read these), files changed
   elsewhere (usually fine), moved or deleted files, and new folders no box covers, grouped by area.
   No drift: stop here.
2. **Checkout at head.** `python3 -I <topo>/pipeline/checkout.py <map> --at head --out <new folder>`.
3. **Re-brief only the affected areas.** Reuse the map's `areas.json` with
   `python3 -I <topo>/pipeline/brief.py` (point its `"checkout"` at the new folder), then add to each
   affected area's brief the drift worklist for it: the boxes to re-read, the moved and deleted paths,
   and the new files to cover. Tell agents to edit their existing slice (keep ids that still fit, so
   connections from other areas stay attached) rather than start over.
4. **Run those agents in parallel** (or one after another, if your tool can't run agents; in Claude Code,
   with `model: "sonnet"` unless the user asks for another); each
   validates its slice against the new checkout. Copy the refreshed slices into `<map>/parts/`, over the
   old ones.
5. **Record the new commits.** Set each refreshed repository's `commit` in `<map>/topo.config.json` to
   the head you mapped, so the next drift run starts from there, and replace `<map>/checkout` with the
   new folder.
6. **Rebuild and check.** `python3 -I <topo>/pipeline/finish.py <map>` validates every slice together,
   lists references with no exact box, builds the page, checks cited lines and writes the analysis; fix
   what it reports in `parts/` and run it again until it passes. For a
   client's map, regenerate its shareable copy with the `share` skill. Read the new `ANALYSIS.md` section
   on integration contracts: a refresh is when a broken contract appears.
