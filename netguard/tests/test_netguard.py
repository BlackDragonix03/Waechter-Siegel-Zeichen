"""Tests für die Logik ohne Netzwerk und ohne GUI. Aufruf: python -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NETGUARD_DATA"] = tempfile.mkdtemp(prefix="netguard-test-")

from netguard import oui, classify, storage, diagnostics  # noqa: E402
from netguard.model import Device, Scan, InterfaceInfo, compare_scans, merge_previous_values, STATUS_NEW, STATUS_MISSING, STATUS_CHANGED, STATUS_SAME  # noqa: E402
from netguard.net import local, discover  # noqa: E402
from netguard.mcp.backend import HeadlessBackend  # noqa: E402
from netguard.mcp.protocol import Session  # noqa: E402
from netguard.mcp.tools import TOOLS, call_tool, tool_descriptions  # noqa: E402
from netguard.ai import ollama  # noqa: E402


class OuiTests(unittest.TestCase):
    def test_lookup(self):
        self.assertEqual(oui.lookup("C8:0E:14:12:34:56"), "AVM")
        self.assertEqual(oui.lookup("b8-27-eb-00-00-00"), "Raspberry Pi")
        self.assertEqual(oui.lookup(""), "")
        self.assertTrue(oui.lookup("02:11:22:33:44:55").startswith("(private"))

    def test_normalize(self):
        self.assertEqual(oui.normalize_mac("C8-0E-14-AB-CD-EF"), "c8:0e:14:ab:cd:ef")


class ClassifyTests(unittest.TestCase):
    def test_gateway_wins(self):
        d = Device(ip="192.168.1.1", is_gateway=True, open_ports=[445, 3389])
        self.assertEqual(classify.classify(d), "router")

    def test_ports(self):
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", open_ports=[9100, 80])), "printer")
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", open_ports=[554, 80])), "camera")
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", open_ports=[135, 445])), "pc")
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", open_ports=[53, 80])), "router")

    def test_vendor_and_names(self):
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", vendor="Synology")), "nas")
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", vendor="Apple")), "phone")
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", vendor="Apple", open_ports=[22, 445])), "pc")
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", hostname="brother-mfc.fritz.box")), "printer")
        self.assertEqual(classify.classify(Device(ip="1.1.1.1", ssdp_type="urn:schemas-upnp-org:device:InternetGatewayDevice:1")), "router")

    def test_admin_url(self):
        self.assertEqual(classify.admin_url(Device(ip="10.0.0.1", open_ports=[80, 443])), "https://10.0.0.1/")
        self.assertEqual(classify.admin_url(Device(ip="10.0.0.1", open_ports=[8080])), "http://10.0.0.1:8080/")
        self.assertEqual(classify.admin_url(Device(ip="10.0.0.1")), "")


class TargetTests(unittest.TestCase):
    def test_expand(self):
        self.assertEqual(local.expand_targets(["192.168.1.0/30"]), ["192.168.1.1", "192.168.1.2"])
        self.assertEqual(local.expand_targets(["10.0.0.1-3"]), ["10.0.0.1", "10.0.0.2", "10.0.0.3"])
        self.assertEqual(local.expand_targets(["10.0.0.1 - 10.0.0.2", "10.0.0.2"]), ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(local.expand_targets(["quatsch"]), [])
        self.assertEqual(len(local.expand_targets(["10.0.0.0/16"], limit=100)), 100)

    def test_subnet_of(self):
        ifaces = [InterfaceInfo("eth0", "192.168.1.5", "255.255.255.0", "192.168.1.1", cidr="192.168.1.0/24")]
        self.assertEqual(local.subnet_of("192.168.1.9", [], ifaces), "192.168.1.0/24")
        self.assertEqual(local.subnet_of("10.1.2.3", ["10.1.0.0/16"], ifaces), "10.1.0.0/16")
        self.assertEqual(local.subnet_of("172.16.5.3", [], ifaces), "172.16.5.0/24")


class DiscoverTests(unittest.TestCase):
    def test_candidates(self):
        quick = discover.candidate_subnets("quick")
        self.assertEqual(len(quick), len(set(quick)))
        self.assertIn("192.168.178.0/24", quick)
        self.assertIn("172.31.255.0/24", quick)
        self.assertIn("10.10.5.0/24", quick)
        self.assertNotIn("10.77.123.0/24", quick)
        full = discover.candidate_subnets("full")
        self.assertIn("10.77.123.0/24", full)
        self.assertGreater(len(full), 65536)

    def test_hints_and_exclude(self):
        c = discover.candidate_subnets("quick", hints=["10.99.4.0/22", "192.168.5.17/24"], exclude=["192.168.0.0/24"])
        self.assertEqual(c[:4], ["10.99.4.0/24", "10.99.5.0/24", "10.99.6.0/24", "10.99.7.0/24"])
        self.assertEqual(c[4], "192.168.5.0/24")
        self.assertNotIn("192.168.0.0/24", c)
        self.assertEqual(len(c), len(set(c)))

    def test_route_networks(self):
        for n in discover.route_networks():
            self.assertIn("/", n)


class CompareTests(unittest.TestCase):
    def test_compare(self):
        cur = Scan(devices=[Device(ip="1.0.0.1", mac="aa:aa:aa:aa:aa:01", hostname="a", open_ports=[80]),
                            Device(ip="1.0.0.9", mac="aa:aa:aa:aa:aa:02"),
                            Device(ip="1.0.0.3")])
        old = Scan(devices=[Device(ip="1.0.0.1", mac="aa:aa:aa:aa:aa:01", hostname="a", open_ports=[80]),
                            Device(ip="1.0.0.2", mac="aa:aa:aa:aa:aa:02"),
                            Device(ip="1.0.0.7", mac="aa:aa:aa:aa:aa:03")])
        diffs = {(d.device.ip): d.status for d in compare_scans(cur, old)}
        self.assertEqual(diffs["1.0.0.1"], STATUS_SAME)
        self.assertEqual(diffs["1.0.0.9"], STATUS_CHANGED)
        self.assertEqual(diffs["1.0.0.3"], STATUS_NEW)
        self.assertEqual(diffs["1.0.0.7"], STATUS_MISSING)

    def test_merge(self):
        cur = Scan(devices=[Device(ip="1.0.0.1", mac="aa:aa:aa:aa:aa:01")])
        old = Scan(devices=[Device(ip="1.0.0.1", mac="aa:aa:aa:aa:aa:01", hostname="router.lan", custom_name="Router", device_type="router", trusted=True)])
        self.assertEqual(merge_previous_values(cur, old), 1)
        d = cur.devices[0]
        self.assertEqual((d.hostname, d.custom_name, d.device_type, d.trusted), ("router.lan", "Router", "router", True))


class StorageTests(unittest.TestCase):
    def test_roundtrip(self):
        scan = Scan(name="Test", targets=["10.0.0.0/24"], devices=[Device(ip="10.0.0.1", mac="aa:bb:cc:dd:ee:ff", services={"80": "HTTP"})],
                    interfaces=[InterfaceInfo("eth0", "10.0.0.2", "255.255.255.0", "10.0.0.1")])
        p = storage.save_scan(scan)
        loaded = storage.load_scan(p)
        self.assertEqual(loaded.name, "Test")
        self.assertEqual(loaded.devices[0].mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(loaded.interfaces[0].gateway, "10.0.0.1")
        self.assertTrue(any(info["id"] == scan.id for _, info in storage.list_scans()))
        storage.delete_scan(p)

    def test_known(self):
        known = {}
        d = Device(ip="10.0.0.5", mac="aa:bb:cc:00:00:01", custom_name="TV", trusted=True, last_seen="2026-01-01T00:00:00")
        storage.remember_device(known, d)
        storage.save_known(known)
        fresh = Device(ip="10.0.0.6", mac="aa:bb:cc:00:00:01")
        storage.apply_known([fresh], storage.load_known())
        self.assertEqual(fresh.custom_name, "TV")
        self.assertTrue(fresh.trusted)


class DiagnosticsTests(unittest.TestCase):
    def test_apipa_and_gateway(self):
        scan = Scan(interfaces=[InterfaceInfo("wlan", "169.254.3.4", "255.255.0.0", "")], gateways=[])
        titles = [p["title"] for p in diagnostics.analyze(scan)]
        self.assertTrue(any("Keine IP-Adresse" in t for t in titles))

    def test_gateway_down(self):
        scan = Scan(interfaces=[InterfaceInfo("eth0", "10.0.0.2", "255.255.255.0", "10.0.0.1")], gateways=["10.0.0.1"],
                    devices=[Device(ip="10.0.0.2", is_self=True, alive_via=["self"])], internet_ok=False)
        sev = {p["title"]: p["severity"] for p in diagnostics.analyze(scan)}
        self.assertEqual(sev.get("Gateway 10.0.0.1 antwortet nicht"), diagnostics.SEV_ERROR)

    def test_double_nat(self):
        scan = Scan(internet_path=["192.168.178.1", "192.168.0.1", "80.1.2.3"], internet_ok=True, dns_ok=True)
        self.assertTrue(any(p["title"] == "Doppeltes NAT erkannt" for p in diagnostics.analyze(scan)))

    def test_ok(self):
        scan = Scan(interfaces=[InterfaceInfo("eth0", "10.0.0.2", "255.255.255.0", "10.0.0.1")], gateways=["10.0.0.1"],
                    devices=[Device(ip="10.0.0.1", is_gateway=True, alive_via=["icmp"], latency_ms=1.0, mac="c8:0e:14:00:00:01")],
                    internet_ok=True, dns_ok=True)
        self.assertEqual(diagnostics.analyze(scan)[0]["severity"], diagnostics.SEV_OK)


class McpTests(unittest.TestCase):
    def setUp(self):
        self.backend = HeadlessBackend()
        scan = Scan(name="MCP", targets=["10.0.0.0/24"], gateways=["10.0.0.1"],
                    interfaces=[InterfaceInfo("eth0", "10.0.0.2", "255.255.255.0", "10.0.0.1", cidr="10.0.0.0/24")],
                    devices=[Device(ip="10.0.0.1", mac="c8:0e:14:00:00:01", is_gateway=True, device_type="router", open_ports=[80, 443]),
                             Device(ip="10.0.0.2", mac="aa:bb:cc:00:00:02", is_self=True, device_type="self"),
                             Device(ip="10.0.0.7", mac="aa:bb:cc:00:00:07", hostname="drucker", device_type="printer", subnet="10.0.0.0/24")],
                    internet_ok=True, dns_ok=True)
        self.backend.set_current_scan(scan)
        self.session = Session(self.backend)

    def test_initialize_and_list(self):
        r = self.session.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", r["result"]["capabilities"])
        self.assertIsNone(self.session.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        r = self.session.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in r["result"]["tools"]}
        self.assertEqual(names, {t.name for t in TOOLS})
        for t in r["result"]["tools"]:
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_tools(self):
        text, err = call_tool(self.backend, "get_devices", {"type": "printer"})
        self.assertFalse(err)
        data = json.loads(text)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["devices"][0]["ip"], "10.0.0.7")
        text, err = call_tool(self.backend, "get_device", {"device": "drucker"})
        self.assertFalse(err)
        self.assertEqual(json.loads(text)["hostname_dns"], "drucker")
        text, err = call_tool(self.backend, "get_topology", {})
        self.assertFalse(err)
        topo = json.loads(text)
        self.assertEqual(topo["root"], "dev:10.0.0.1")
        self.assertTrue(any(e["parent"] == "dev:10.0.0.1" and e["child"] == "dev:10.0.0.7" for e in topo["edges"]))
        text, err = call_tool(self.backend, "set_device_info", {"device": "10.0.0.7", "name": "Büro-Drucker", "trusted": True})
        self.assertFalse(err)
        self.assertEqual(self.backend.current_scan().device_by_ip("10.0.0.7").custom_name, "Büro-Drucker")
        text, err = call_tool(self.backend, "get_problems", {})
        self.assertFalse(err)
        self.assertIn("problems", json.loads(text))
        text, err = call_tool(self.backend, "get_device", {"device": "gibtsnicht"})
        self.assertTrue(err)
        text, err = call_tool(self.backend, "scan_network", {"discover": "falsch"})
        self.assertTrue(err)

    def test_rpc_errors(self):
        r = self.session.handle({"jsonrpc": "2.0", "id": 5, "method": "unbekannt"})
        self.assertEqual(r["error"]["code"], -32601)
        r = self.session.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "nope"}})
        self.assertTrue(r["result"]["isError"])
        r = self.session.handle([{"jsonrpc": "2.0", "id": 7, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"}])
        self.assertEqual(len(r), 1)


class OllamaTests(unittest.TestCase):
    def test_tools_conversion(self):
        t = ollama.tools_for_ollama(tool_descriptions())
        self.assertEqual(len(t), len(TOOLS))
        self.assertEqual(t[0]["type"], "function")
        self.assertIn("parameters", t[0]["function"])

    def test_chat_loop(self):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if any(m.get("role") == "tool" for m in body["messages"]):
                    out = {"message": {"role": "assistant", "content": "Antwort: " + body["messages"][-1]["content"]}}
                else:
                    out = {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "echo", "arguments": {"x": 1}}}]}}
                b = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            msgs = [{"role": "user", "content": "hi"}]
            events = []
            text = ollama.chat(msgs, "m", [{"type": "function", "function": {"name": "echo", "parameters": {}}}],
                               lambda n, a: (f"{n}:{a['x']}", False), f"http://127.0.0.1:{srv.server_port}",
                               on_event=lambda a, t: events.append(a))
            self.assertEqual(text, "Antwort: echo:1")
            self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "tool", "assistant"])
            self.assertEqual(events, ["tool", "result", "text"])
        finally:
            srv.shutdown()

    def test_unavailable(self):
        ok, msg = ollama.available("http://127.0.0.1:1")
        self.assertFalse(ok)
        self.assertIn("Ollama", msg)


if __name__ == "__main__":
    unittest.main()
