"""Tests for pipeline/leakscan.py, with made-up names only.
usage (from topo/): python3 -I -m unittest discover -s test -p 'test_*.py'
"""
import importlib.util
import json
import os
import unittest

_spec = importlib.util.spec_from_file_location(
    "leakscan", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline", "leakscan.py"))
leakscan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(leakscan)

PATS = leakscan.compile_patterns({
    "leak_scan": [r"\bacme\b", "northwind traders", r"\bzed"],
    "rules": [["Contoso", "Fabrikam"], [r"\bglobex\b", "initech", "case"]],
})


def lines(text):
    return [line for _, line, _, _ in leakscan.find(text, PATS)]


class Find(unittest.TestCase):
    def test_separators_and_camel_case(self):
        for text in ["scripts/extract_acme_ftue.py", "acme-dashboard", "ACME_KEY", "AcmeDashboard",
                     "loadAcmeConfig", "HTTPAcme", "titles/acme.json", "ShardsZed"]:
            self.assertTrue(lines(text), text)

    def test_longer_words_pass(self):
        for text in ["acmeless", "pacmen", "Fabrikam", "the zero point", "initech"]:
            self.assertFalse(lines(text), text)

    def test_rule_sources_keep_their_case_flag(self):
        self.assertTrue(lines("a Contoso report"))
        self.assertFalse(lines("a contoso report"))  # rule without "case" is case-sensitive
        self.assertTrue(lines("GLOBEX and Globex"))

    def test_phrases_and_line_numbers(self):
        self.assertEqual(lines("one\ntwo\nNorthwind Traders\n"), [3])
        self.assertEqual(lines("x\nextract_acme_ftue.py\n"), [2])

    def test_one_hit_per_pattern_and_line(self):
        self.assertEqual(len(leakscan.find("acme acme_acme", PATS)), 1)


class Allow(unittest.TestCase):
    ALLOW = [("NOTICE", "northwind traders"), ("docs/*.md", r"\bacme\b")]

    def test_only_the_named_pattern_in_the_named_file(self):
        self.assertTrue(leakscan.allowed("NOTICE", "northwind traders", self.ALLOW))
        self.assertTrue(leakscan.allowed("docs/about.md", r"\bacme\b", self.ALLOW))
        self.assertFalse(leakscan.allowed("README.md", "northwind traders", self.ALLOW))
        self.assertFalse(leakscan.allowed("NOTICE", r"\bacme\b", self.ALLOW))
        self.assertFalse(leakscan.allowed("NOTICE", "northwind traders", []))

    def test_rules_files_merge_their_allowances(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for k, allow in enumerate([[["NOTICE", "northwind traders"]], []]):
                p = os.path.join(d, f"r{k}.json")
                json.dump({"leak_scan": ["northwind traders"], "allow": allow}, open(p, "w"))
                paths.append(p)
            self.assertEqual(leakscan.load_blob(paths)["allow"], [("NOTICE", "northwind traders")])


class PrivateFiles(unittest.TestCase):
    def test_names_under_targets(self):
        for p in ["topo/maps/x/rules.json", "topo/maps/x/client-rules.json", "topo/maps/x/generalized.json",
                  "topo/maps/x/figures-worklist.json", "topo/maps/x/topo-data.json", "topo/private/notes.md"]:
            self.assertTrue(leakscan.private_file(p), p)
        # outside the targets a rules file is someone else's business; in Topo's own repository everything is a target
        outside = ["site/rules.json"] if leakscan.TARGETS != [""] else []
        for p in ["topo/maps/x/flows.json", "topo/pipeline/SCHEMA.md"] + outside:
            self.assertFalse(leakscan.private_file(p), p)

    def test_rules_shape_anywhere(self):
        self.assertTrue(leakscan.rules_shaped("site/data.json", b'{"rules": [], "leak_scan": []}'))
        self.assertFalse(leakscan.rules_shaped("site/data.json", b'{"rules": []}'))
        self.assertFalse(leakscan.rules_shaped("notes.md", b'{"rules": [], "leak_scan": []}'))


class Staged(unittest.TestCase):
    """The pre-commit run: map files staged on a machine with no private rules are held back."""

    def run_hook(self, root, home, rules=None):
        import subprocess
        import sys
        env = {"PATH": os.environ["PATH"], "HOME": home, "TOPO_SCAN_ROOT": root, "TOPO_SCAN_TARGETS": ""}
        if rules:
            env["TOPO_RULES"] = rules
        return subprocess.run([sys.executable, "-I", leakscan.__file__, "--staged"], env=env, capture_output=True, text=True)

    def test_map_files_need_the_rules(self):
        import json
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root, home = os.path.join(d, "repo"), os.path.join(d, "home")
            os.makedirs(os.path.join(root, "maps", "x"))
            os.makedirs(home)
            subprocess.run(["git", "init", "-q", root], check=True)
            with open(os.path.join(root, "README.md"), "w") as f:
                f.write("hello\n")
            subprocess.run(["git", "-C", root, "add", "README.md"], check=True)
            self.assertEqual(self.run_hook(root, home).returncode, 0)   # no map files: nothing to hold back
            with open(os.path.join(root, "maps", "x", "flows.json"), "w") as f:
                f.write("{}\n")
            subprocess.run(["git", "-C", root, "add", "-A"], check=True)
            r = self.run_hook(root, home)
            self.assertEqual(r.returncode, 1)
            self.assertIn("changes 1 map file", r.stdout)
            rules = os.path.join(d, "rules.json")
            with open(rules, "w") as f:
                json.dump({"leak_scan": ["northwind traders"]}, f)
            self.assertEqual(self.run_hook(root, home, rules).returncode, 0, self.run_hook(root, home, rules).stdout)


class PrivateFolder(unittest.TestCase):
    """pipeline/settings.py: one setting says where the private folder is; a machine can require rules."""

    def run(self, *a, **k):   # every case gets its own home and config, never the caller's
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.d = d
            self.home = os.path.join(d, "home")
            os.makedirs(self.home)
            return super().run(*a, **k)

    def env(self, **extra):
        return {"PATH": os.environ["PATH"], "HOME": self.home, **extra}

    def scan(self, path, **extra):
        import subprocess
        import sys
        return subprocess.run([sys.executable, "-I", leakscan.__file__, path], env=self.env(**extra), capture_output=True, text=True)

    def settings(self, *args, **extra):
        import subprocess
        import sys
        tool = os.path.join(os.path.dirname(leakscan.__file__), "settings.py")
        return subprocess.run([sys.executable, "-I", tool, *args], env=self.env(**extra), capture_output=True, text=True)

    def test_the_depth_of_new_maps(self):
        self.assertIn("depth of new maps: standard (not chosen yet)", self.settings().stdout)
        # saving it keeps the file's other settings
        self.write(os.path.join(self.home, ".config", "topo", "config.json"), '{"private": "~/p"}')
        self.assertEqual(self.settings("--set-depth", "overview").returncode, 0)
        with open(os.path.join(self.home, ".config", "topo", "config.json")) as f:
            self.assertEqual(json.load(f), {"private": "~/p", "depth": "overview"})
        self.assertIn("depth of new maps: overview (from ", self.settings().stdout)
        self.assertNotEqual(self.settings("--set-depth", "bottomless").returncode, 0)
        cfg = self.write(os.path.join(self.home, ".config", "topo", "config.json"), '{"depth": "deep"}')
        self.assertIn("depth of new maps: deep", self.settings().stdout)
        self.assertIn("depth of new maps: overview", self.settings(TOPO_DEPTH="overview").stdout)
        self.write(cfg, '{"depth": "bottomless"}')
        r = self.settings()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not one of overview, standard, deep", r.stderr)

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_where_the_folder_comes_from(self):
        self.assertIn(os.path.join(self.home, ".topo", "private") + " (from the default)", self.settings().stdout)
        cfg = self.write(os.path.join(self.home, ".config", "topo", "config.json"), '{"private": "~/secret"}')
        self.assertIn(os.path.join(self.home, "secret") + f" (from {cfg})", self.settings().stdout)
        self.assertIn("/elsewhere (from $TOPO_PRIVATE)", self.settings(TOPO_PRIVATE="/elsewhere").stdout)
        other = self.write(os.path.join(self.d, "other.json"), '{"private": "/other"}')
        self.assertIn("/other (from " + other, self.settings(TOPO_CONFIG=other).stdout)
        self.write(other, "not json")
        self.assertNotEqual(self.settings(TOPO_CONFIG=other).returncode, 0)   # a broken setting stops the tools

    def test_rules_come_from_the_private_folder(self):
        target = self.write(os.path.join(self.d, "doc.md"), "a note about Northwind Traders\n")
        self.assertIn("names not checked", self.scan(target).stdout)
        self.write(os.path.join(self.home, "secret", "acme", "rules.json"), '{"leak_scan": ["northwind traders"]}')
        r = self.scan(target, TOPO_PRIVATE=os.path.join(self.home, "secret"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("LEAK", r.stdout)

    def test_a_machine_that_requires_rules_fails_without_them(self):
        target = self.write(os.path.join(self.d, "doc.md"), "nothing private here\n")
        self.assertEqual(self.scan(target).returncode, 0)
        r = self.scan(target, TOPO_REQUIRE_RULES="1")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("this machine requires them", r.stdout)
        self.write(os.path.join(self.home, ".config", "topo", "config.json"), '{"require_rules": true}')
        self.assertEqual(self.scan(target).returncode, 1)
        self.write(os.path.join(self.home, ".topo", "private", "rules.json"), '{"leak_scan": ["northwind traders"]}')
        self.assertEqual(self.scan(target).returncode, 0, self.scan(target).stdout)


if __name__ == "__main__":
    unittest.main()
