"""Tests that this repository stays a working Claude Code plugin and its own marketplace.
usage (from the repository root): python3 -I -m unittest discover -s test -p 'test_*.py'
"""
import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Plugin(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())

    def test_the_marketplace_holds_this_plugin(self):
        (entry,) = self.market["plugins"]
        self.assertEqual(entry["source"], "./")
        self.assertEqual(entry["name"], self.manifest["name"])   # a mismatch makes the install fail
        self.assertTrue(self.market["owner"]["name"])

    def skills(self):
        folder = ROOT / self.manifest["skills"]
        self.assertTrue(self.manifest["skills"].startswith("./") and folder.is_dir())
        return sorted(folder.glob("*/SKILL.md"))

    def test_codex_finds_the_same_plugin(self):
        codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
        market = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
        (entry,) = market["plugins"]
        self.assertEqual((entry["name"], entry["source"]), (codex["name"], {"source": "local", "path": "./"}))
        for key in ("name", "description", "license", "skills"):
            self.assertEqual(codex[key], self.manifest[key], key)

    def test_both_plugins_start_the_map_server(self):
        server = self.manifest["mcpServers"]["topo"]
        self.assertEqual(server["args"], ["-I", "${CLAUDE_PLUGIN_ROOT}/pipeline/mcp_server.py"])
        codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())
        conf = json.loads((ROOT / codex["mcpServers"]).read_text())["mcpServers"]["topo"]
        self.assertEqual((conf["args"], conf["cwd"]), (["-I", "pipeline/mcp_server.py"], "."))   # cwd: the plugin's root
        self.assertTrue((ROOT / "pipeline" / "mcp_server.py").exists())
        # a .mcp.json at the root would also start in every Claude Code session opened in this clone
        self.assertFalse((ROOT / ".mcp.json").exists())

    def test_every_skill_is_named_for_its_folder(self):
        names = []
        for f in self.skills():
            front = re.match(r"---\n(.*?)\n---\n", f.read_text(), re.S).group(1)
            name = re.search(r"^name: (\S+)$", front, re.M).group(1)
            self.assertEqual(name, f.parent.name)
            self.assertRegex(front, r"(?m)^description: .{40,}")
            names.append(name)
        self.assertEqual(names, ["map", "refresh", "share"])

    def test_skills_run_from_any_folder(self):
        # installed as a plugin, Claude runs in the user's project: every tool goes through <topo>
        for f in self.skills():
            text = f.read_text()
            self.assertIn("${CLAUDE_PLUGIN_ROOT}", text, f)
            # other tools have no such variable: the skill says where Topo is relative to itself
            self.assertIn(f"three folders above this file", text, f)
            self.assertEqual(f.relative_to(ROOT).parts[:2], (".claude", "skills"))
        # mapping agents default to Sonnet in Claude Code; the depth check holds them to the same bar
        for name in ("map", "refresh"):
            self.assertIn('model: "sonnet"', (ROOT / ".claude/skills" / name / "SKILL.md").read_text())
            for bad in re.findall(r"python3 -I (?!<topo>/)\S+", text):
                self.fail(f"{f.parent.name}: '{bad}' runs a tool by a path relative to Topo's folder")
            for ref in re.findall(r"<topo>/([\w./-]+[\w])", text):
                self.assertTrue((ROOT / ref).exists(), f"{f.parent.name}: <topo>/{ref} does not exist")


if __name__ == "__main__":
    unittest.main()
