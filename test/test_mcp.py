"""Tests for the MCP server (pipeline/mcp_server.py): the protocol over stdio, and what each tool answers
about a small map that the server builds on first use.
usage (from the repository root): python3 -I -m unittest discover -s test -p 'test_*.py'
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline", "mcp_server.py")


def session(calls, maps, cwd=None):
    """Run the server for one session: initialize, list the tools, then each (tool, arguments) call."""
    msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]
    msgs += [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": n, "arguments": a}}
             for i, (n, a) in enumerate(calls, 2)]
    env = dict(os.environ, TOPO_MAPS=maps, HOME=maps)   # no ~/topo-maps of the machine running the tests
    r = subprocess.run([sys.executable, "-I", SERVER], input="".join(json.dumps(m) + "\n" for m in msgs),
                       capture_output=True, text=True, env=env, cwd=cwd, timeout=60)
    replies = {x["id"]: x for x in map(json.loads, r.stdout.splitlines())}
    return replies


def answer(reply):
    res = reply["result"]
    text = res["content"][0]["text"]
    return (text if res["isError"] else json.loads(text)), res["isError"]


class Server(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.t = os.path.realpath(self.tmp.name)
        self.clone = os.path.join(t, "shop")
        os.makedirs(os.path.join(self.clone, "src"))
        subprocess.run(["git", "init", "-q", self.clone], check=True)
        m = self.map = os.path.join(t, "maps", "shop")
        os.makedirs(os.path.join(m, "parts"))
        Path(m, "topo.config.json").write_text(json.dumps({
            "title": "Shop", "regions": [{"id": "app:shop", "rect": [0, 0, 100, 100]}],
            "repos": [{"key": "app:shop", "name": "Shop", "commit": "a" * 40, "url": "https://github.com/acme/shop"}]}))
        Path(m, "clones.json").write_text(json.dumps({"app:shop": self.clone}))
        Path(m, "skeleton.json").write_text(json.dumps({"nodes": [
            {"id": "app:shop", "name": "Shop", "kind": "app", "summary": "The shop."},
            {"id": "shop.orders", "parent": "app:shop", "name": "Orders", "kind": "group", "summary": "Orders."}]}))
        Path(m, "parts", "core.json").write_text(json.dumps({"area": "core", "nodes": [
            {"id": "f:src/orders.py", "parent": "shop.orders", "name": "Order views", "kind": "module",
             "summary": "Lists and places orders.", "paths": ["src/orders.py"]},
            {"id": "f:src/orders.py#list_orders", "parent": "f:src/orders.py", "name": "list_orders", "kind": "function",
             "summary": "Returns the orders.", "paths": ["src/orders.py:1"]},
            {"id": "f:src/orders.py#place_order", "parent": "f:src/orders.py", "name": "place_order", "kind": "function",
             "summary": "Places an order and charges the card.", "paths": ["src/orders.py:10-30"]},
            {"id": "f:src/pay.py#charge", "parent": "shop.orders", "name": "charge", "kind": "function",
             "summary": "Charges a card.", "paths": ["src/pay.py:4"]}],
            "edges": [{"from": "f:src/orders.py#place_order", "to": "f:src/pay.py#charge", "kind": "calls",
                       "label": "charges the card", "evidence": "src/orders.py:22"}],
            "flows": [{"id": "flow.core.buy", "name": "A shopper buys", "summary": "From order to charge.",
                       "steps": [{"node": "f:src/orders.py#place_order", "text": "The order is placed."},
                                 {"node": "f:src/pay.py#charge", "text": "The card is charged."}]}]}))
        self.maps = os.path.join(t, "maps")

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_protocol(self):
        r = session([("no_such_tool", {})], self.maps)
        self.assertEqual(r[0]["result"]["serverInfo"]["name"], "topo")
        tools = {t["name"]: t for t in r[1]["result"]["tools"]}
        self.assertEqual(sorted(tools), ["topo_analysis", "topo_box", "topo_connections", "topo_find", "topo_flow",
                                         "topo_maps", "topo_owner"])
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools.values()))
        self.assertIn("error", r[2])
        self.assertNotIn(1, [k for k in r if "error" in r[k] and k != 2])

    def test_a_map_answers_about_its_code(self):
        r = session([
            ("topo_owner", {"path": os.path.join(self.clone, "src", "orders.py"), "line": 15}),
            ("topo_owner", {"path": "src/orders.py:5"}),
            ("topo_box", {"id": "f:src/orders.py#place_order"}),
            ("topo_connections", {"id": "f:src/pay.py#charge", "direction": "in"}),
            ("topo_find", {"query": "charge card", "map": "shop"}),
            ("topo_flow", {"id": "flow.core.buy"}),
            ("topo_owner", {"path": "src/nowhere.py"}),
        ], self.maps)
        # an absolute path in the map's clone, and a line inside a cited range
        owner, err = answer(r[2])
        self.assertFalse(err, owner)
        (o,) = owner["owners"]
        self.assertEqual((o["map"], o["path"], o["box"]["id"]), ("shop", "src/orders.py", "f:src/orders.py#place_order"))
        self.assertEqual(o["box"]["in"], "Shop > Orders > Order views")
        # a box that cites only its first line runs until the next box in the file starts
        owner, _ = answer(r[3])
        self.assertEqual(owner["owners"][0]["box"]["id"], "f:src/orders.py#list_orders")
        box, _ = answer(r[4])
        self.assertEqual(box["calls_out"][0]["to"]["id"], "f:src/pay.py#charge")
        self.assertEqual(box["paths"][0]["url"], f"https://github.com/acme/shop/blob/{'a' * 40}/src/orders.py#L10-L30")
        self.assertEqual(box["paths"][0]["local"], os.path.join(self.clone, "src/orders.py") + ":10-30")
        self.assertEqual(box["flows"], [{"id": "flow.core.buy", "name": "A shopper buys"}])
        self.assertEqual(box["mapped_at"][0]["mapped_at"], "a" * 12)
        conn, _ = answer(r[5])
        self.assertEqual(conn["depended_on_by"][0]["from"]["id"], "f:src/orders.py#place_order")
        found, _ = answer(r[6])
        self.assertEqual(found["results"][0]["id"], "f:src/pay.py#charge")
        flow, _ = answer(r[7])
        self.assertEqual([s["id"] for s in flow["steps"]], ["f:src/orders.py#place_order", "f:src/pay.py#charge"])
        missing, err = answer(r[8])
        self.assertTrue(err)
        self.assertIn("no box cites src/nowhere.py", missing)
        # the server built the map's data on first use, without touching its page
        self.assertTrue(os.path.exists(os.path.join(self.map, "topo-data.json")))
        self.assertFalse(os.path.exists(os.path.join(self.map, "dist")))

    def test_which_map_when_there_are_several(self):
        other = os.path.join(self.maps, "other")
        os.makedirs(os.path.join(other, "parts"))
        for f in ("topo.config.json", "skeleton.json"):
            Path(other, f).write_text(Path(self.map, f).read_text())
        Path(other, "parts", "x.json").write_text(json.dumps({"area": "x", "nodes": [
            {"id": "f:src/x.py", "parent": "shop.orders", "name": "X", "kind": "module", "summary": "X.",
             "paths": ["src/x.py"]}], "edges": []}))
        r = session([("topo_box", {"id": "f:src/pay.py#charge"}), ("topo_flow", {})], self.maps)
        box, err = answer(r[2])
        self.assertEqual(box["map"], "shop")              # the only map with that box
        msg, err = answer(r[3])
        self.assertTrue(err)
        self.assertIn("several maps", msg)
        r = session([("topo_flow", {})], self.maps, cwd=self.clone)
        flows, err = answer(r[2])
        self.assertEqual(flows["map"], "shop")            # the map whose clone the client works in


if __name__ == "__main__":
    unittest.main()
