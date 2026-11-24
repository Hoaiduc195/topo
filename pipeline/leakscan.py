"""Leak guard: keep private files and client names out of the shared repository.

usage:
  python3 -I leakscan.py [--rules RULES.json ...] [PATH ...]   scan PATHs (default: what git would commit under the targets)
  python3 -I leakscan.py --staged                               pre-commit: scan what is about to be committed

Two checks:
1. Private files, which needs no private material: a rules file, figures overlay, worklist or
   merged data under a target (`*rules*.json`, `generalized.json`, `*worklist*.json`,
   `topo-data.json`, anything in a `private/` folder), and any JSON file anywhere in the
   repository that carries both `rules` and `leak_scan` keys.
2. Names: every `leak_scan` pattern (case-insensitive) is matched twice, against the text as
   written and against a copy with identifiers split into words (`_ - / .` and camelCase become
   spaces), so `\\bacme\\b` also catches `extract_acme_frames.py` and `AcmeDashboard`. Every
   rule's source pattern is matched against the text as written, with the rule's own case flag.

Rules come from --rules, else $TOPO_RULES (paths separated by ':'), else rules.json and */rules.json
in this machine's private folder (pipeline/settings.py: $TOPO_PRIVATE, the config file, else
~/.topo/private). With no rules the name check is skipped, unless the machine requires rules
("require_rules" in the config file, or $TOPO_REQUIRE_RULES=1): then the scan fails.

A rules file may also allow a name in a given file, for one that is meant to be public there (a
copyright line, say): `"allow": [[path glob, pattern as written in leak_scan or rules], ...]`. The
allowance lives with the private rules, so the shared repository never spells out the name.

What it scans follows where it sits: Topo's own repository is scanned whole; a topo/ folder inside a
larger repository is scanned with the .claude/skills/ folder next to it. Set it explicitly with
$TOPO_SCAN_ROOT (the repository), $TOPO_SCAN_TARGETS (path prefixes separated by ':') and
$TOPO_SCAN_ANYWHERE=0 (rules-shaped JSON outside the targets is allowed, as in a private bundle).
"""
import argparse
import fnmatch
import glob
import json
import os
import re
import subprocess
import sys
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # -I leaves the script's folder off the path
import settings  # noqa: E402

TOPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.basename(TOPO) == "topo" and os.path.isdir(os.path.join(os.path.dirname(TOPO), ".git")):
    # inside a larger repository, as a topo/ folder: scan Topo and the shared folders next to it
    ROOT = os.path.dirname(TOPO)
    TARGETS = ["topo/", ".claude/skills/"]
else:
    # Topo's own repository: everything in it is shared
    ROOT = TOPO
    TARGETS = [""]
if os.environ.get("TOPO_SCAN_ROOT"):
    ROOT = os.path.abspath(os.path.expanduser(os.environ["TOPO_SCAN_ROOT"]))
if os.environ.get("TOPO_SCAN_TARGETS") is not None:
    TARGETS = os.environ["TOPO_SCAN_TARGETS"].split(":")
ANYWHERE = os.environ.get("TOPO_SCAN_ANYWHERE", "1") != "0"   # rules-shaped JSON is private wherever it is
PRIVATE_NAMES = ["*rules*.json", "generalized.json", "*worklist*.json", "topo-data.json"]
SEPARATORS = re.compile(r"[_\-/.]")
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def split_words(text):
    """Same number of lines as `text`, with identifiers split into words."""
    return CAMEL.sub(" ", SEPARATORS.sub(" ", text))


def compile_patterns(blob):
    """blob: {"leak_scan": [pattern, ...], "rules": [[pattern, replacement(, "case")], ...]}"""
    pats = [(re.compile(p, re.IGNORECASE), True) for p in blob.get("leak_scan", [])]
    for r in blob.get("rules", []):
        case = len(r) > 2 and r[2] == "case"
        pats.append((re.compile(r[0], re.IGNORECASE if case else 0), False))
    return pats


def find(text, pats):
    """[(pattern index, line number, start, end)] for every match, once per pattern and line.
    start and end index `text` for matches as written and are None for split-word matches."""
    hits, seen = [], set()
    variants = [(text, True)]
    split = split_words(text)
    if split != text:
        variants.append((split, False))
    for body, as_written in variants:
        starts = [0] + [m.end() for m in re.finditer("\n", body)]
        for i, (rx, words_too) in enumerate(pats):
            if not as_written and not words_too:
                continue
            for m in rx.finditer(body):
                line = bisect_right(starts, m.start())
                if (i, line) not in seen:
                    seen.add((i, line))
                    hits.append((i, line, m.start() if as_written else None, m.end() if as_written else None))
    return sorted(hits, key=lambda h: (h[1], h[0]))


def rules_paths(given):
    if given:
        return given
    if os.environ.get("TOPO_RULES"):
        return os.environ["TOPO_RULES"].split(":")
    home = settings.private_dir()
    return [p for p in [os.path.join(home, "rules.json")] + sorted(glob.glob(os.path.join(home, "*", "rules.json"))) if os.path.exists(p)]


def load_blob(paths):
    blob = {"leak_scan": [], "rules": [], "allow": []}
    for p in paths:
        raw = json.load(open(p))
        blob["leak_scan"] += raw.get("leak_scan", [])
        blob["rules"] += [r[:1] + [""] + r[2:] for r in raw.get("rules", [])]  # replacements are not needed to scan
        blob["allow"] += [tuple(a[:2]) for a in raw.get("allow", [])]
    return blob


def allowed(path, pattern, allow):
    """True when a rules file allows `pattern` (its source, as written) in the file at `path`."""
    return any(pattern == p and fnmatch.fnmatch(path, glob) for glob, p in allow)


def git(*args, binary=False):
    out = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, check=True).stdout
    return out if binary else out.decode()


def in_targets(path):
    return any(path == t or path.startswith(t) for t in TARGETS)


def private_file(path):
    name = os.path.basename(path).lower()
    return in_targets(path) and ("private" in path.split("/")[:-1] or any(fnmatch.fnmatch(name, p) for p in PRIVATE_NAMES))


def rules_shaped(path, data):
    if not path.endswith(".json"):
        return False
    try:
        doc = json.loads(data)
    except ValueError:
        return False
    return isinstance(doc, dict) and "rules" in doc and "leak_scan" in doc


def candidates(staged, paths):
    """(path for reports, bytes) for each file to check."""
    if staged:
        names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0")
        for n in filter(None, names):
            yield n, git("show", f":{n}", binary=True)
        return
    if paths:
        for p in paths:
            files = [p] if os.path.isfile(p) else [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs]
            for f in sorted(files):
                yield os.path.relpath(os.path.abspath(f), ROOT), open(f, "rb").read()
        return
    names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    for n in filter(None, names):
        if (in_targets(n) or (ANYWHERE and n.endswith(".json"))) and os.path.isfile(os.path.join(ROOT, n)):
            yield n, open(os.path.join(ROOT, n), "rb").read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--rules", action="append")
    ap.add_argument("--staged", action="store_true")
    a = ap.parse_args()
    found = rules_paths(a.rules)
    blob = load_blob(found) if found else None

    pats = compile_patterns(blob) if blob else []
    allow = blob["allow"] if blob else []
    problems = files = 0
    needs_names = []
    for path, data in candidates(a.staged, a.paths):
        files += 1
        if private_file(path) or ((ANYWHERE or in_targets(path)) and rules_shaped(path, data)):
            problems += 1
            print(f"PRIVATE FILE {path}: never commit it")
            continue
        if not (in_targets(path) or a.paths) or b"\0" in data[:8192]:
            continue
        if any(path.startswith(t + "maps/") for t in TARGETS):   # maps/ here, topo/maps/ in a larger repository
            needs_names.append(path)
        text = data.decode("utf-8", errors="replace")
        for i, line, s, e in find(text, pats):
            if allowed(path, pats[i][0].pattern, allow):
                continue
            problems += 1
            ctx = text[max(0, s - 40):e + 40].replace("\n", " ") if s is not None else "(after splitting identifiers into words)"
            print(f"LEAK {path}:{line} /{pats[i][0].pattern}/: {ctx}")

    if not pats:
        msg = "names not checked: no private rules available"
        where = f"Put the rules in {settings.private_dir()} (set the folder with $TOPO_PRIVATE or the config file;\n" \
                f"python3 -I {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.py')} shows it) or set TOPO_RULES"
        if settings.require_rules():
            print(f"leakscan: {msg}, and this machine requires them (require_rules).\n{where}, then try again.")
            sys.exit(1)
        if a.staged and needs_names:
            print(f"leakscan: {msg}, and this commit changes {len(needs_names)} map file(s).\n"
                  f"{where}, then commit again. (A clone that\n"
                  "keeps no private maps does not need this hook: remove it from .git/hooks/pre-commit.)")
            sys.exit(1)
        elif not a.staged:
            print(f"leakscan: {msg}")
    print(f"leakscan: {files} file(s), {len(pats)} pattern(s), {problems} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
