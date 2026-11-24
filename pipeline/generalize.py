"""Generalize business figures in a shareable map (users, revenue, prices, rates...).

Names are handled by anonymize.py; figures need judgment (a 60 s timeout stays, 48,000 daily
users doesn't), so rewriting is done by an agent or a person and stored as an OVERLAY that is
re-applied after every anonymization run. The worklist and the overlay quote the text before
generalization, figures included, so both live in the PRIVATE folder next to the named sources,
never in the shareable map folder:

  python3 -I pipeline/generalize.py scan  MAP_DIR --out PRIVATE/<map>/worklist.json      # fields to review
  python3 -I pipeline/generalize.py apply MAP_DIR --overlay PRIVATE/<map>/generalized.json
  python3 -I pipeline/generalize.py check MAP_DIR                                          # what still looks like a figure

`scan` lists every text field holding a number near a business word; the reviewer returns
{key: new_text} for the fields they change (keys are copied from the worklist). `apply` rewrites
the map's slices in place and then runs `check`, which prints sentences that still look like
business figures so a person can confirm they are technical.

The first `apply` pins each entry to the text it replaces ({"text": ..., "was": ...}). Later runs
skip and list any entry whose field no longer reads as `was`: the source changed after review, so
the replacement may be out of date. Re-review it, update `text`, and set `was` to the field's new
text (or delete `was` to re-pin on the next run).

Keys: n|<node id>|<field>  n|<node id>|facts|<i>  e|<from>|<to>|<kind>|<field>  f|<flow id>|<step>
"""
import argparse
import glob
import json
import os
import re
import sys

BUSINESS = re.compile(
    r"(user|player|payer|spender|install|DAU|MAU|download|revenue|\$|€|£|USD|EUR|price|priced|pricing|"
    r"cost per|CPI|eCPI|ROI|ROAS|return on|ARPU|ARPPU|LTV|lifetime value|retention|retained|\bD\d{1,3}\b|"
    r"day-\d+|conversion|CVR|churn|whale|dolphin|minnow|spend|sales|purchas|IAP|engaged|participation|"
    r"completion|completed|win rate|winrate|cohort|uplift|lift|budget|per month|monthly|gross|net |"
    r"bookings|paying|monetiz)", re.I)
NUMBER = re.compile(r"(?<![\w.])(?:[$€£]\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:%|k\b|K\b|M\b|x\b)|"
                    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\b\d{3,}\b)")


def files(mdir):
    return sorted(glob.glob(os.path.join(mdir, "parts", "*.json"))) + \
        [p for p in (os.path.join(mdir, "skeleton.json"), os.path.join(mdir, "flows.json")) if os.path.exists(p)]


def fields(doc):
    """Yield (key, container, field, index) for every reviewable text field in a slice."""
    for n in doc.get("nodes", []):
        for f in ("name", "summary", "detail", "signature", "code"):
            if isinstance(n.get(f), str):
                yield f"n|{n['id']}|{f}", n, f, None
        for i, fact in enumerate(n.get("facts", []) or []):
            if isinstance(fact, str):
                yield f"n|{n['id']}|facts|{i}", n, "facts", i
    for e in doc.get("edges", []):
        for f in ("label", "detail"):
            if isinstance(e.get(f), str):
                yield f"e|{e.get('from')}|{e.get('to')}|{e.get('kind')}|{f}", e, f, None
    for fl in doc.get("flows", []) or []:
        for i, st in enumerate(fl.get("steps", [])):
            if isinstance(st.get("text"), str):
                yield f"f|{fl['id']}|{i}", st, "text", None
        if isinstance(fl.get("summary"), str):
            yield f"f|{fl['id']}|summary", fl, "summary", None


def get(obj, f, i):
    return obj[f][i] if i is not None else obj[f]


def put(obj, f, i, v):
    if i is not None:
        obj[f][i] = v
    else:
        obj[f] = v


# dates and years are not figures: 2026-07-14, 07-28, March 2026
DATES = re.compile(r"\b(?:19|20)\d{2}(?:-\d{2}){0,2}\b|\b\d{2}-\d{2}\b")


def figure_like(text):
    t = DATES.sub(" ", text)
    return bool(NUMBER.search(t) and BUSINESS.search(t))


def suspicious_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.;!?])\s+|\n", text) if figure_like(s)]


def inside(path, folder):
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(folder)]) == os.path.realpath(folder)
    except ValueError:  # different drives on Windows
        return False


def cmd_scan(a):
    if not a.out:
        sys.exit("scan: pass --out PRIVATE/<map>/worklist.json (the worklist quotes the figures, so keep it private)")
    if inside(a.out, a.map_dir):
        sys.exit("scan: --out is inside the shareable map folder; write the worklist to the private folder instead")
    work = []
    for p in files(a.map_dir):
        doc = json.load(open(p))
        for key, obj, f, i in fields(doc):
            t = get(obj, f, i)
            if figure_like(t):
                work.append({"key": key, "file": os.path.basename(p), "text": t})
    json.dump(work, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{len(work)} fields to review -> {a.out}")


def cmd_apply(a):
    if not a.overlay:
        sys.exit("apply: pass --overlay PRIVATE/<map>/generalized.json")
    if inside(a.overlay, a.map_dir):
        sys.exit("apply: the overlay quotes the original figures; keep it in the private folder, not the map folder")
    overlay = json.load(open(a.overlay))
    used, stale, applied, already, pinned = set(), [], 0, 0, 0
    for p in files(a.map_dir):
        doc = json.load(open(p))
        changed = False
        for key, obj, f, i in fields(doc):
            if key not in overlay:
                continue
            entry, cur = overlay[key], get(obj, f, i)
            if isinstance(entry, str):
                # first apply: remember the text this replaces, to spot later source changes
                entry = overlay[key] = {"text": entry, **({"was": cur} if cur != entry else {})}
                pinned += 1
            used.add(key)
            if cur == entry["text"]:
                already += 1
            elif "was" in entry and entry["was"] != cur:
                stale.append(key)
            else:
                put(obj, f, i, entry["text"])
                applied += 1
                changed = True
        if changed:
            json.dump(doc, open(p, "w"), ensure_ascii=False, indent=1)
    if pinned:
        json.dump(overlay, open(a.overlay, "w"), ensure_ascii=False, indent=1)
    missing = sorted(set(overlay) - used)
    print(f"applied {applied} of {len(overlay)} overlay entries ({already} already applied, {pinned} newly pinned)")
    for k in missing[:20]:
        print("  not found (the map changed since the overlay was written):", k)
    if stale:
        print(f"{len(stale)} entr{'y' if len(stale) == 1 else 'ies'} skipped: the field changed after review "
              "(compare `was` with the map, then update `text` and `was`):")
        for k in stale:
            print("  stale:", k)
    cmd_check(a)
    if stale or missing:
        sys.exit(1)


def cmd_check(a):
    left = []
    for p in files(a.map_dir):
        doc = json.load(open(p))
        for key, obj, f, i in fields(doc):
            for s in suspicious_sentences(get(obj, f, i)):
                left.append((key, s))
    print(f"{len(left)} sentence(s) still look like business figures; confirm each is technical:")
    for key, s in left[: (None if a.all else 40)]:
        print(f"  {key.split('|')[1][:60]} | {s[:170]}")


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("cmd", choices=["scan", "apply", "check"])
    ap.add_argument("map_dir")
    ap.add_argument("--out")
    ap.add_argument("--overlay")
    ap.add_argument("--all", action="store_true", help="print every remaining sentence")
    a = ap.parse_args()
    {"scan": cmd_scan, "apply": cmd_apply, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
