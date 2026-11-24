---
name: share
description: Regenerate the anonymized, figure-generalized copy of a private Topo map from its private sources, with the leak guard, and run every check. Use after any change to a map's private sources, before committing a shareable map, or when a leak scan flags a name.
---

# Regenerate the shareable copy safely

`<topo>` below is the folder Topo is installed in, the one that holds `pipeline/`. In Claude Code it is
`${CLAUDE_PLUGIN_ROOT}`. If that still reads as a placeholder rather than a folder (in Codex, a clone of
Topo or any other tool), `<topo>` is three folders above this file, which sits at
`<topo>/.claude/skills/<skill>/SKILL.md`.

This is for maps of code that cannot be published as it is, such as a client's: an anonymized copy is
written to `<shared>/<map>`, a folder in the repository where shareable maps are committed (`maps/` in
a Topo clone), and the named sources stay in a private folder outside it (`<private>` below:
`$TOPO_PRIVATE`, else `"private"` in `~/.config/topo/config.json`, else `~/.topo/private`;
`python3 -I <topo>/pipeline/settings.py` prints it). A map of your own repositories needs none of this.

Never edit the shareable copy by hand. Change the private sources in `<private>/<map>/`, then:

1. `python3 -I <topo>/pipeline/anonymize.py --rules <private>/rules.json --src <private>/<map> --out <shared>/<map>`
   It fails on any name the rules miss, including names inside identifiers. When it does, add a rule
   (and a `leak_scan` pattern) to the private rules file and run it again. Never reword the copy.
2. `python3 -I <topo>/pipeline/generalize.py apply <shared>/<map> --overlay <private>/<map>/generalized.json`
   Stale entries mean the source text changed: re-review them, never force them. Then read every
   sentence it flags as a possible figure (`generalize.py check <shared>/<map> --all`); only new ones
   need review. Technical numbers stay; users, revenue, prices, conversion and retention become
   qualitative, through new overlay entries.
3. `validate.py`, `build.py` and `analyze.py` from `<topo>/pipeline/` on `<shared>/<map>`, then the leak
   guard over what the repository would commit: `python3 -I <topo>/pipeline/leakscan.py` from that
   repository's root (`TOPO_SCAN_ROOT` names another root).
4. In a Topo clone, `sh test/run.sh` runs all of it again with the tests and the browser smoke test, and
   fails if the regenerated copy differs from what is committed.
5. Commit only paths you changed (other sessions may share the checkout). The pre-commit hook scans what
   you stage; install it once per clone with `sh <topo>/hooks/install.sh`.
