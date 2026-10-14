"""Tests für die Logik ohne Netzwerk und ohne GUI. Aufruf: python -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["NETGUARD_DATA"] = tempfile.mkdtemp(prefix="netguard-test-")

from netguard import oui, classify, storage, diagnostics  # noqa: E402
from netguard.model import Device, Scan, InterfaceInfo, compare_scans, merge_previous_values, STATUS_NEW, STATUS_MISSING, STATUS_CHANGED, STATUS_SAME  # noqa: E402
from netguard.net import local  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
