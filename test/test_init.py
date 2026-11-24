"""Tests for pipeline/init.py on throwaway git repositories.
usage (from the repository root): python3 -I -m unittest discover -s test -p 'test_*.py'
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PIPE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline")


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def tool(name, *args, **env):
    # never this machine's Topo settings (its default depth, say): a config file that isn't there
    clean = {k: v for k, v in os.environ.items() if not k.startswith("TOPO_")}
    clean["TOPO_CONFIG"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "no-such-config.json")
    return subprocess.run([sys.executable, "-I", os.path.join(PIPE, name), *args], capture_output=True, text=True,
                          env={**clean, **env})


def repo(root, files, remote=None):
    os.makedirs(root)
    sh(root, "git", "init", "-q")
    sh(root, "git", "config", "user.email", "t@example.invalid")
    sh(root, "git", "config", "user.name", "t")
    for path, text in files.items():
        Path(root, path).parent.mkdir(parents=True, exist_ok=True)
        Path(root, path).write_text(text)
    sh(root, "git", "add", "-A")
    sh(root, "git", "commit", "-q", "-m", "c")
    if remote:
        sh(root, "git", "remote", "add", "origin", remote)
    return sh(root, "git", "rev-parse", "HEAD").strip()


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())   # git reports real paths (/private/var on macOS)

    def load(self, out, name):
        return json.loads(Path(out, name).read_text())

    def test_one_repository_makes_a_map_that_builds(self):
        api = os.path.join(self.tmp, "shop-api")
        head = repo(api, {
            "README.md": "# Shop\n\n[![ci](x.svg)](y)\n\nShop API serves the catalog and checkout over HTTP. More text.\n",
            "src/app.py": "def main():\n    pass\n",
            "src/orders/views.py": "def list_orders():\n    return []\n",
            "Dockerfile": "FROM python\n",
        }, remote="https://user:secret-token@github.com/acme-co/shop-api.git")
        Path(api, "src/app.py").write_text("def main():\n    return 1\n")   # uncommitted: not mapped
        out = os.path.join(self.tmp, "map")
        r = tool("init.py", api, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("uncommitted changes are not mapped", r.stdout)

        cfg = self.load(out, "topo.config.json")
        (rp,) = cfg["repos"]
        self.assertEqual((rp["key"], rp["commit"], rp["url"]), ("app:shop-api", head, "https://github.com/acme-co/shop-api"))
        self.assertNotIn("prefix", rp)
        self.assertNotIn("secret-token", json.dumps(cfg))
        self.assertEqual([g["id"] for g in cfg["regions"]], ["app:shop-api", "ext"])
        skel = self.load(out, "skeleton.json")["nodes"]
        self.assertEqual(skel[0]["summary"], "Shop API serves the catalog and checkout over HTTP.")
        self.assertEqual(self.load(out, "clones.json"), {"app:shop-api": api})
        # the checkout is the commit, not the working tree
        self.assertEqual(Path(out, "checkout/src/app.py").read_text(), "def main():\n    pass\n")
        orient = Path(out, "ORIENT.md").read_text()
        for text in ("`src/` 2", "`Dockerfile`", "`src/app.py`", "Suggested mapping agents:** 1",
                     "**Depth:** standard", "2 public definitions"):
            self.assertIn(text, orient)
        self.assertEqual(cfg["depth"], "standard")

        # nothing can edit the snapshot the map is checked against
        self.assertFalse(os.access(os.path.join(out, "checkout/src/app.py"), os.W_OK))

        # an agent's slice: finish.py merges it into parts/, validates it against the checkout, builds the
        # page and checks its cited lines, in one step
        slice_ = {"area": "api", "nodes": [
            {"id": "f:src/orders/views.py", "parent": "app:shop-api", "name": "Order views", "kind": "module",
             "summary": "Lists orders.", "detail": "One view that returns the orders.",
             "paths": ["src/orders/views.py:1"]},
            {"id": "f:src/orders/views.py#list_orders", "parent": "f:src/orders/views.py", "name": "list_orders",
             "kind": "function", "summary": "Returns the orders.", "paths": ["src/orders/views.py:1-2"],
             "code": "def list_orders():\n    return []"},
            {"id": "f:src/app.py#main", "parent": "app:shop-api", "name": "main", "kind": "function",
             "summary": "Starts the app.", "paths": ["src/app.py:1-2"], "code": "def main():\n    pass"}],
            "edges": [{"from": "f:src/app.py#main", "to": "f:src/orders/views.py#list_orders", "kind": "calls",
                       "label": "lists the orders", "evidence": "src/app.py:1"}]}
        os.makedirs(os.path.join(out, "slices"))
        Path(out, "slices/api.json").write_text(json.dumps(slice_))
        f = tool("finish.py", out, "--merge")
        self.assertEqual(f.returncode, 0, f.stdout + f.stderr)
        self.assertTrue(os.path.exists(os.path.join(out, "parts", "api.json")))
        self.assertTrue(os.path.exists(os.path.join(out, "dist", "index.html")))
        self.assertTrue(os.path.exists(os.path.join(out, "ANALYSIS.md")))
        self.assertIn("finish: validate OK (0 warnings); unresolved references: none; symbols 2/2 (100%); "
                      "public definitions with a box 2/2", f.stdout)

        # the merge step's edits in parts/ survive another merge; a symbol citing the wrong line fails
        slice_["nodes"][1]["paths"] = ["src/app.py:1"]
        Path(out, "parts/api.json").write_text(json.dumps(slice_))
        f = tool("finish.py", out, "--merge", "--no-analyze")
        self.assertIn("kept parts/api.json", f.stdout)
        self.assertEqual(f.returncode, 1)
        self.assertIn("symbols 1/2 (50%)", f.stdout)

        # a map that could hold every public definition but leaves one out is too shallow
        del slice_["nodes"][2]
        slice_["edges"] = []
        slice_["nodes"][1]["paths"] = ["src/orders/views.py:1-2"]
        Path(out, "parts/api.json").write_text(json.dumps(slice_))
        f = tool("finish.py", out, "--no-analyze")
        self.assertEqual(f.returncode, 1)
        self.assertIn("public definitions with a box: 1/2 (50%)", f.stdout)
        self.assertIn("src/app.py: main", f.stdout)

        # an agent sent back edits its slice after the merge: the newer slice replaces the copy in parts/
        good = dict(slice_, nodes=slice_["nodes"] + [
            {"id": "f:src/app.py#main", "parent": "app:shop-api", "name": "main", "kind": "function",
             "summary": "Starts the app.", "paths": ["src/app.py:1-2"], "code": "def main():\n    pass"}])
        Path(out, "slices/api.json").write_text(json.dumps(good))
        later = os.path.getmtime(os.path.join(out, "parts/api.json")) + 5
        os.utime(os.path.join(out, "slices/api.json"), (later, later))
        f = tool("finish.py", out, "--merge", "--no-analyze")
        self.assertIn("updated parts/api.json", f.stdout)
        self.assertTrue(os.path.exists(os.path.join(out, ".merge-backup", "api.json")))
        self.assertEqual(json.loads(Path(out, "parts/api.json").read_text()), good)

        # a slice that doesn't validate stops before the build
        Path(out, "parts/api.json").write_text(json.dumps({"area": "api", "nodes": [{"id": "f:src/nowhere.py"}]}))
        f = tool("finish.py", out)
        self.assertEqual(f.returncode, 1)
        self.assertIn("validation failed", f.stdout)
        self.assertNotIn("== build", f.stdout)

        again = tool("init.py", api, "--out", out)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("already holds a map", again.stderr)

    def test_the_depth_comes_from_the_flag_else_the_machine(self):
        api = os.path.join(self.tmp, "api")
        repo(api, {"main.py": "def serve():\n    pass\n\ndef stop():\n    pass\n"})
        out = os.path.join(self.tmp, "deep")
        self.assertEqual(tool("init.py", api, "--out", out, TOPO_DEPTH="deep").returncode, 0)
        self.assertEqual(self.load(out, "topo.config.json")["depth"], "deep")
        self.assertIn("one per area of about 100 public definitions", Path(out, "ORIENT.md").read_text())
        out = os.path.join(self.tmp, "overview")
        self.assertEqual(tool("init.py", api, "--out", out, "--depth", "overview", TOPO_DEPTH="deep").returncode, 0)
        self.assertEqual(self.load(out, "topo.config.json")["depth"], "overview")
        # a depth of the machine's own goes into the map in full
        cfg = os.path.join(self.tmp, "config.json")
        Path(cfg).write_text(json.dumps({"depths": {"review": {"symbols": 0.4, "about": "main functions"}}}))
        out = os.path.join(self.tmp, "review")
        r = tool("init.py", api, "--out", out, "--depth", "review", TOPO_CONFIG=cfg)
        self.assertEqual(r.returncode, 0, r.stderr)
        kept = self.load(out, "topo.config.json")["depth"]
        self.assertEqual((kept["name"], kept["symbols"], kept["cap"]), ("review", 0.4, 75))
        self.assertIn("**Depth:** review: main functions", Path(out, "ORIENT.md").read_text())
        r = tool("init.py", api, "--out", os.path.join(self.tmp, "x"), "--depth", "bottomless")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not one of overview, standard, deep", r.stderr)

    def test_several_repositories_get_folders_and_a_url_is_cloned(self):
        a = os.path.join(self.tmp, "web")
        b = os.path.join(self.tmp, "worker")
        repo(a, {"index.ts": "export {}\n"}, remote="git@github.com:acme-co/web.git")
        repo(b, {"main.go": "package main\n"})
        out = os.path.join(self.tmp, "map")
        r = tool("init.py", a, "file://" + b, "--name", "Acme Systems", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        cfg = self.load(out, "topo.config.json")
        self.assertEqual([(x["key"], x["prefix"], x["url"]) for x in cfg["repos"]],
                         [("app:web", "web/", "https://github.com/acme-co/web"), ("app:worker", "worker/", None)])
        self.assertEqual(cfg["title"], "acme-systems")
        self.assertTrue(os.path.exists(os.path.join(out, "checkout", "web", "index.ts")))
        self.assertTrue(os.path.exists(os.path.join(out, "checkout", "worker", "main.go")))
        self.assertEqual(self.load(out, "clones.json")["app:worker"], os.path.join(out, "clones", "worker"))
        left, right = cfg["regions"][0]["rect"], cfg["regions"][1]["rect"]
        self.assertLess(left[2], right[0])

    def test_remotes_on_each_host_become_links(self):
        sys.path.insert(0, PIPE)
        try:
            import init
        finally:
            sys.path.remove(PIPE)
        cases = {
            "https://user:token@github.com/acme-co/web.git": ("github", "https://github.com/acme-co/web", "acme-co/web"),
            "git@github.com:acme-co/web.git": ("github", "https://github.com/acme-co/web", "acme-co/web"),
            "https://gitlab.com/acme-co/platform/api.git": ("gitlab", "https://gitlab.com/acme-co/platform/api", "acme-co/platform/api"),
            "git@gitlab.com:acme-co/api.git": ("gitlab", "https://gitlab.com/acme-co/api", "acme-co/api"),
            "ssh://git@gitlab.example.com:2222/team/api.git": ("gitlab", "https://gitlab.example.com/team/api", "team/api"),
            "https://user@bitbucket.org/acme-co/api.git": ("bitbucket", "https://bitbucket.org/acme-co/api", "acme-co/api"),
            "git@bitbucket.org:acme-co/api.git": ("bitbucket", "https://bitbucket.org/acme-co/api", "acme-co/api"),
        }
        for remote, want in cases.items():
            self.assertEqual(init.web_remote(remote), want, remote)
        for remote in ("", "/srv/git/api.git", "file:///srv/git/api", "https://git.example.com/team/api.git",
                       "https://github.com/acme-co/web/extra.git"):
            self.assertIsNone(init.web_remote(remote), remote)

        api = os.path.join(self.tmp, "api")
        repo(api, {"main.py": "pass\n"}, remote="git@gitlab.com:acme-co/platform/api.git")
        out = os.path.join(self.tmp, "map")
        r = tool("init.py", api, "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        (rp,) = self.load(out, "topo.config.json")["repos"]
        self.assertEqual((rp["url"], rp["host"]), ("https://gitlab.com/acme-co/platform/api", "gitlab"))
        self.assertEqual(self.load(out, "skeleton.json")["nodes"][0]["repo"], "acme-co/platform/api")

    def test_not_a_repository(self):
        os.makedirs(os.path.join(self.tmp, "plain"))
        r = tool("init.py", os.path.join(self.tmp, "plain"), "--out", os.path.join(self.tmp, "map"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a git repository", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "map")))


if __name__ == "__main__":
    unittest.main()
