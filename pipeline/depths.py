"""The depths a map can be made at: overview, standard and deep, plus any a machine or a map defines.

usage: python3 -I pipeline/depths.py          lists the depths this machine knows, with their floors
       python3 -I pipeline/depths.py --help   prints this: how to define a depth of your own
       python3 -I pipeline/depths.py --show D what a map's topo.config.json keeps as its "depth" for D

The built-in depths are in depths.json next to this file. A machine adds its own under "depths" in
Topo's config file (see settings.py), and a map's topo.config.json can carry one inline as "depth":

  "depths": {"review": {"based_on": "standard", "symbols": 0.4, "excerpts": 6,
                        "about": "the main functions only, for a quick review"}}

A depth names a built-in one to start from ("based_on", standard when left out) and changes any of:

  about             one line on what a map at this depth shows
  symbols           0 to 1: the share of an area's public definitions that need a symbol box
  cap               count at most this many of an area's public definitions (null: all of them)
  every_definition  "always", "when_it_fits" or "never": when the map as a whole must box at least
                    65% of every public definition (when_it_fits: when they fit in half the boxes its
                    areas hold)
  connect           "symbols" (symbol boxes must have connections) or "files" (file boxes, counting a
                    connection from a box inside them)
  excerpts          code excerpts each area needs
  agents            how many mapping agents to suggest: ["code_files", N] (one per N code files),
                    ["public_definitions", N] (one per N public definitions) or ["boxes"] (by size)

No depth can turn the precision checks off: every box cites real files and lines, every symbol box cites
its line, and cited lines must match their symbols.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILT_IN = os.path.join(HERE, "depths.json")
FIELDS = ("about", "symbols", "cap", "every_definition", "connect", "excerpts", "agents")
DEFAULT = "standard"


class DepthError(ValueError):
    pass


def built_in():
    with open(BUILT_IN, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def check_level(name, level):
    """The level, complete and valid, or DepthError saying what's wrong."""
    missing = [f for f in FIELDS if f not in level]
    if missing:
        raise DepthError(f"depth {name!r} has no {', '.join(missing)}")
    if not isinstance(level["symbols"], (int, float)) or not 0 <= level["symbols"] <= 1:
        raise DepthError(f"depth {name!r}: symbols must be a share from 0 to 1")
    if level["cap"] is not None and (not isinstance(level["cap"], int) or level["cap"] < 0):
        raise DepthError(f"depth {name!r}: cap must be a whole number of definitions, or null")
    if level["every_definition"] not in ("always", "when_it_fits", "never"):
        raise DepthError(f"depth {name!r}: every_definition must be always, when_it_fits or never")
    if level["connect"] not in ("symbols", "files"):
        raise DepthError(f"depth {name!r}: connect must be symbols or files")
    if not isinstance(level["excerpts"], int) or level["excerpts"] < 0:
        raise DepthError(f"depth {name!r}: excerpts must be a whole number")
    a = level["agents"]
    if not (isinstance(a, list) and a and (a == ["boxes"] or (len(a) == 2 and a[0] in ("code_files", "public_definitions")
                                                              and isinstance(a[1], int) and a[1] > 0))):
        raise DepthError(f"depth {name!r}: agents must be [\"boxes\"], [\"code_files\", N] or [\"public_definitions\", N]")
    return level


def build(name, spec, known):
    """A full level from a spec that may name a built-in one to start from."""
    if not isinstance(spec, dict):
        raise DepthError(f"depth {name!r} must be an object")
    unknown = set(spec) - set(FIELDS) - {"based_on", "name"}
    if unknown:
        raise DepthError(f"depth {name!r}: unknown {', '.join(sorted(unknown))}")
    base = spec.get("based_on", DEFAULT)
    if base not in known:
        raise DepthError(f"depth {name!r} is based on {base!r}, which is not one of {', '.join(known)}")
    return check_level(name, {**known[base], **{k: v for k, v in spec.items() if k in FIELDS}, "name": name})


def levels():
    """Every depth this machine knows: the built-in ones, then the config file's "depths"."""
    known = {k: check_level(k, {**v, "name": k}) for k, v in built_in().items()}
    sys.path.insert(0, HERE)
    import settings
    for name, spec in (settings.config().get("depths") or {}).items():
        if name in known and name in built_in():
            raise DepthError(f"depth {name!r} is built in; give yours another name")
        known[name] = build(name, spec, {k: v for k, v in known.items() if k in built_in()})
    return known


def resolve(value):
    """A depth as a full level: a name this machine knows, or an object (a map's own depth)."""
    if value is None:
        value = DEFAULT
    if isinstance(value, dict):
        name = value.get("name", "custom")
        base = {k: v for k, v in built_in().items()}
        return build(name, {k: v for k, v in value.items()}, {k: {**v, "name": k} for k, v in base.items()})
    known = levels()
    if value not in known:
        raise DepthError(f"depth {value!r} is not one of {', '.join(known)}")
    return known[value]


def stored(level):
    """How a map's config keeps its depth: a built-in one by name, any other in full, so the map still
    knows its floors on a machine that never heard of that depth."""
    if level["name"] in built_in() and all(level[f] == built_in()[level["name"]][f] for f in FIELDS):
        return level["name"]
    return {"name": level["name"], **{f: level[f] for f in FIELDS}}


def agents(level, code_files, defs, standard_agents):
    """How many mapping agents to suggest at a depth, as text."""
    kind = level["agents"][0]
    if kind == "code_files":
        return str(max(1, math.ceil(code_files / level["agents"][1])))
    if kind == "public_definitions":
        return str(max(1, math.ceil(defs / level["agents"][1])))
    return standard_agents


def floors(level):
    """One line on what the depth check asks at a depth."""
    if level["symbols"]:
        cap = f", counting at most {level['cap']}" if level["cap"] is not None else ""
        sym = f"symbol boxes for {level['symbols']:.0%} of each area's public definitions{cap}"
    else:
        sym = "no symbol boxes required"
    return f"{sym}; {level['connect']} connected; {level['excerpts']} excerpts an area"


if __name__ == "__main__":
    if sys.argv[1:] in (["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "--show":
        try:
            print(json.dumps(stored(resolve(sys.argv[2]))))
        except DepthError as e:
            sys.exit(f"depths: {e}")
        sys.exit(0)
    try:
        for name, lv in levels().items():
            print(f"{name}: {lv['about']}\n    {floors(lv)}")
    except DepthError as e:
        sys.exit(f"depths: {e}")
