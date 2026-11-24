"""Skim a Python source tree into Topo boxes: packages as groups, each module with what its docstring
says, its documented public classes and functions, and the imports between modules.

usage: python3 -I pipeline/skim.py ROOT DIR [DIR ...] --prefix P --parent ID --id-prefix S --out slice.json

A skim is not a mapping run. It reads what the code says about itself (docstrings, signatures,
imports), not how it works, so maps label a skimmed application as such. Use it to give a system
real structure until it is mapped with the map skill.
"""
import argparse
import ast
import glob
import json
import os
import re

MAX_SYMBOLS = 15


def sentence(text, limit):
    """The first sentence of a docstring, at most `limit` characters, cut at a word."""
    first = re.split(r"(?<=[.!?])\s|\n\s*\n", " ".join((text or "").strip().split("\n\n")[0].split()), maxsplit=1)[0]
    first = first.strip().rstrip(":")
    if len(first) <= limit:
        return first
    return first[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def paragraph(text, limit):
    para = " ".join((text or "").strip().split("\n\n")[0].split())
    return para if len(para) <= limit else para[:limit - 1].rsplit(" ", 1)[0] + "…"


def role_name(doc, stem):
    """A role name of at most 48 characters: the docstring's first sentence, or the part of it before a
    colon or dash ("Agent caller" from "Agent caller: orchestrates..."), else the file name in words."""
    first = sentence(doc, 200).rstrip(".")
    heads = [first.split(sep)[0] for sep in (" — ", ": ", " - ") if sep in first]
    for cand in heads + [first] + [first.split(sep)[0] for sep in (" (", ", ")]:
        cand = cand.strip().rstrip(".").strip("`")
        if 3 <= len(cand) <= 48:
            return cand[0].upper() + cand[1:]
    return stem.replace("_", " ").capitalize()


def signature(node):
    try:
        args = ast.unparse(node.args)
    except Exception:  # noqa: BLE001 - an odd signature is no reason to drop the box
        args = "..."
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    ret = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    return f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({args}){ret}"


def skim(root, dirs, *, prefix, parent, id_prefix, repo_key=None, extras=()):
    """(nodes, edges) for the Python packages under `dirs` (relative to `root`), cited as prefix + path.

    `extras` are (glob, kind, group name) for non-Python files worth a box each (workflows, configs).
    """
    nodes, edges, groups, modules = [], [], {}, {}

    def group_for(rel_dir, top):
        if rel_dir in groups:
            return groups[rel_dir]
        up = os.path.dirname(rel_dir)
        par = group_for(up, top) if rel_dir != top and up else parent
        gid = f"{id_prefix}." + re.sub(r"[^a-z0-9]+", "-", rel_dir.lower()).strip("-")
        init = os.path.join(root, rel_dir, "__init__.py")
        doc = ""
        if os.path.exists(init):
            try:
                with open(init, encoding="utf-8") as fh:
                    doc = ast.get_docstring(ast.parse(fh.read())) or ""
            except SyntaxError:
                doc = ""
        node = {"id": gid, "parent": par, "name": os.path.basename(rel_dir)[:48], "kind": "group",
                "summary": sentence(doc, 200) or f"The {os.path.basename(rel_dir)} package.", "paths": [prefix + rel_dir + "/"]}
        if doc:
            node["detail"] = paragraph(doc, 1200)
        if repo_key and par == parent:
            node["repo_key"] = repo_key
        nodes.append(node)
        groups[rel_dir] = gid
        return gid

    for top in dirs:
        for path in sorted(glob.glob(os.path.join(root, top, "**", "*.py"), recursive=True)):
            rel = os.path.relpath(path, root)
            base = os.path.basename(rel)
            if "__pycache__" in rel or "/tests/" in "/" + rel or base.startswith("test_") or base == "__init__.py":
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
            except SyntaxError:
                continue
            doc = ast.get_docstring(tree) or ""
            gid = group_for(os.path.dirname(rel), top)
            mid = f"f:{prefix}{rel}"
            mod = {"id": mid, "parent": gid, "name": role_name(doc, base[:-3]), "kind": "module",
                   "summary": sentence(doc, 200) or f"{base} (no module docstring).", "paths": [prefix + rel]}
            if doc and len(paragraph(doc, 1200)) > len(mod["summary"]) + 20:
                mod["detail"] = paragraph(doc, 1200)
            nodes.append(mod)
            dotted = rel[:-3].replace(os.sep, ".")
            modules[dotted] = mid
            count = 0
            for item in tree.body:
                if count >= MAX_SYMBOLS:
                    break
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or item.name.startswith("_"):
                    continue
                sdoc = ast.get_docstring(item)
                if not sdoc:
                    continue
                count += 1
                is_class = isinstance(item, ast.ClassDef)
                nodes.append({"id": f"{mid}#{item.name}", "parent": mid, "name": (item.name if is_class else item.name + "()")[:48],
                              "kind": "class" if is_class else "function", "summary": sentence(sdoc, 200),
                              "signature": signature(item)[:400], "paths": [f"{prefix}{rel}:{item.lineno}"]})
            mod["_imports"] = [(n.lineno, n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
            mod["_dotted"] = dotted

    seen = set()
    for mod in [n for n in nodes if "_imports" in n]:
        pkg = mod["_dotted"].rsplit(".", 1)[0]
        for lineno, imp in mod.pop("_imports"):
            targets = []
            if isinstance(imp, ast.ImportFrom):
                if imp.level:
                    base = pkg.split(".")
                    base = base[:len(base) - (imp.level - 1)] if imp.level > 1 else base
                    stem = ".".join(base + ([imp.module] if imp.module else []))
                else:
                    stem = imp.module or ""
                targets += [stem] + [f"{stem}.{a.name}" for a in imp.names]
            else:
                targets += [a.name for a in imp.names]
            for t in targets:
                for cand in (t, *[k for k in modules if k.endswith("." + t)]):
                    if cand in modules and modules[cand] != mod["id"] and (mod["id"], modules[cand]) not in seen:
                        seen.add((mod["id"], modules[cand]))
                        edges.append({"from": mod["id"], "to": modules[cand], "kind": "calls", "label": "imports",
                                      "evidence": f"{mod['paths'][0]}:{lineno}"})
                        break
        mod.pop("_dotted", None)

    for pattern, kind, gname in extras:
        files = sorted(glob.glob(os.path.join(root, pattern)))
        if not files:
            continue
        gid = f"{id_prefix}." + re.sub(r"[^a-z0-9]+", "-", gname.lower()).strip("-")
        gnode = {"id": gid, "parent": parent, "name": gname[:48], "kind": "group",
                 "summary": f"{len(files)} {gname.lower()}.", "paths": [prefix + os.path.dirname(os.path.relpath(files[0], root)) + "/"]}
        if repo_key:
            gnode["repo_key"] = repo_key
        nodes.append(gnode)
        for f in files:
            rel = os.path.relpath(f, root)
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read(4000)
            m = re.search(r"^(?:description|summary):\s*[\"']?(.+?)[\"']?\s*$", text, re.M)
            nodes.append({"id": f"f:{prefix}{rel}", "parent": gid, "name": os.path.splitext(os.path.basename(rel))[0][:48],
                          "kind": kind, "summary": sentence(m.group(1), 200) if m else f"{os.path.basename(rel)}.", "paths": [prefix + rel]})
    return nodes, edges


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("root")
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--parent", required=True)
    ap.add_argument("--id-prefix", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    nodes, edges = skim(os.path.expanduser(a.root), a.dirs, prefix=a.prefix, parent=a.parent, id_prefix=a.id_prefix)
    json.dump({"area": a.id_prefix, "nodes": nodes, "edges": edges}, open(a.out, "w"), indent=1)
    print(f"skim: {len(nodes)} boxes, {len(edges)} imports")


if __name__ == "__main__":
    main()
