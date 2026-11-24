"""Where this machine keeps private material, as one setting every Topo tool reads.

usage: python3 -I pipeline/settings.py      prints the private folder, where the setting came from,
                                            whether the leak guard requires private rules, and
                                            the depth new maps get (and whether anyone chose it)
       python3 -I pipeline/settings.py --set-depth overview|standard|deep
                                            saves the depth new maps get on this machine

A map of a client's systems keeps its named sources, name rules and figures overlay in a private
folder outside the shared repository. Its place is, in order:

  1. $TOPO_PRIVATE
  2. "private" in the config file: $TOPO_CONFIG, else $XDG_CONFIG_HOME/topo/config.json, else
     ~/.config/topo/config.json
  3. ~/.topo/private

The config file is per machine and belongs to no repository:

  {"private": "~/path/to/private", "require_rules": true, "depth": "deep"}

"depth" (or $TOPO_DEPTH) is how deep new maps go unless one asks for another: overview, standard (the
default), deep, or one of the machine's own, defined under "depths" (depths.py says how). The map skill
passes it to init.py, which writes it into the map's config.

"require_rules" (or $TOPO_REQUIRE_RULES=1) makes the leak guard fail when it finds no name rules,
instead of skipping the name check. Set it on every machine that keeps private maps, so a moved or
missing rules file can never turn the name check off without anyone noticing.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT = "~/.topo/private"


def config_path():
    if os.environ.get("TOPO_CONFIG"):
        return os.path.expanduser(os.environ["TOPO_CONFIG"])
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "topo", "config.json")


def config():
    """The config file's settings, or {} when there is none. A file that is not JSON stops the tool:
    guessing past a broken setting could leave the name check off."""
    path = config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        sys.exit(f"topo settings: cannot read {path}: {e}")
    if not isinstance(data, dict):
        sys.exit(f"topo settings: {path} must hold a JSON object")
    return data


def private_dir_and_source():
    if os.environ.get("TOPO_PRIVATE"):
        return os.path.expanduser(os.environ["TOPO_PRIVATE"]), "$TOPO_PRIVATE"
    c = config()
    if c.get("private"):
        return os.path.expanduser(str(c["private"])), config_path()
    return os.path.expanduser(DEFAULT), "the default"


def private_dir():
    """The folder that holds this machine's private maps, rules and overlays."""
    return private_dir_and_source()[0]


def require_rules():
    """True on a machine that keeps private maps: the leak guard must find name rules there."""
    if os.environ.get("TOPO_REQUIRE_RULES") is not None:
        return os.environ["TOPO_REQUIRE_RULES"] not in ("", "0")
    return bool(config().get("require_rules"))


def depth_and_source():
    """(depth, where it came from): $TOPO_DEPTH, the config file, or "not chosen yet" (standard)."""
    if os.environ.get("TOPO_DEPTH"):
        value, source = os.environ["TOPO_DEPTH"], "$TOPO_DEPTH"
    elif config().get("depth"):
        value, source = config()["depth"], config_path()
    else:
        value, source = "standard", "not chosen yet"
    known = depth_names()
    if value not in known:
        sys.exit(f"topo settings: depth {value!r} is not one of {', '.join(known)}")
    return value, source


def depth_names():
    """The depths this machine knows: overview, standard, deep and the config file's "depths"."""
    import depths
    try:
        return list(depths.levels())
    except depths.DepthError as e:
        sys.exit(f"topo settings: {e}")


def depth():
    """How deep new maps go on this machine unless one asks for another."""
    return depth_and_source()[0]


def set_depth(value):
    """Save how deep new maps go on this machine, keeping the config file's other settings."""
    known = depth_names()
    if value not in known:
        sys.exit(f"topo settings: depth {value!r} is not one of {', '.join(known)}")
    path = config_path()
    data = config()
    data["depth"] = value
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=1) + "\n")
    return path


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--set-depth":
        print(f"depth of new maps: {sys.argv[2]} (saved in {set_depth(sys.argv[2])})")
        sys.exit(0)
    if len(sys.argv) > 1:
        sys.exit("usage: python3 -I pipeline/settings.py [--set-depth <depth>]")
    folder, source = private_dir_and_source()
    print(f"private folder: {folder} (from {source}){'' if os.path.isdir(folder) else ', which does not exist'}")
    print(f"leak guard requires private rules: {'yes' if require_rules() else 'no'}")
    value, where = depth_and_source()
    print(f"depth of new maps: {value} ({'not chosen yet' if where == 'not chosen yet' else 'from ' + where}); "
          f"depths: {', '.join(depth_names())}")
