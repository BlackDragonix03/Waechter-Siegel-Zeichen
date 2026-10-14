"""Scan-Ablauf: Erreichbarkeit, MAC, Namen, Ports, UPnP, Traceroute, Bewertung."""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from ..model import Device, Scan, now_iso
from .. import oui, classify, diagnostics
from . import local, ping as pingmod, arp as arpmod, names as namesmod, ports as portsmod, ssdp as ssdpmod, trace as tracemod

ProgressCb = Callable[[str, int, int, str], None]
DeviceCb = Callable[[Device], None]


@dataclass
class ScanOptions:
    targets: list[str] = field(default_factory=list)   # leer = automatisch
    ping_timeout_ms: int = 600
    workers: int = 96
    resolve_names: bool = True
    netbios: bool = True
    mdns: bool = True
    port_mode: str = "quick"      # "none" | "quick" | "full"
    http_titles: bool = True
    upnp: bool = True
    traceroute: bool = True       # Pfad ins Internet und zu fremden Subnetzen
    trace_all: bool = False       # Pfad zu jedem Gerät (langsam)
    internet_check: bool = True
    max_hosts: int = 4096


class ScanCancelled(Exception):
    pass


class Scanner:
    def __init__(self, options: ScanOptions, progress: ProgressCb | None = None, on_device: DeviceCb | None = None):
        self.opt = options
        self._progress = progress or (lambda *a: None)
        self._on_device = on_device or (lambda d: None)
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._stop.set()

    @property
    def cancelled(self) -> bool:
        return self._stop.is_set()

    def _check(self) -> None:
        if self._stop.is_set():
            raise ScanCancelled()

    def _prog(self, phase: str, done: int, total: int, msg: str = "") -> None:
        self._progress(phase, done, total, msg)

    # ------------------------------------------------------------------
    def run(self) -> Scan:
        t0 = time.time()
        scan = Scan()
        scan.options = {k: v for k, v in self.opt.__dict__.items()}
        self._prog("Netzwerk erkennen", 0, 1, "Schnittstellen und Gateways ermitteln")
        ifaces = local.interfaces()
        scan.interfaces = ifaces
        scan.gateways = local.gateways(ifaces)
        targets = [t for t in self.opt.targets if t.strip()] or local.default_targets(ifaces)
        scan.targets = targets
        own = local.own_ips(ifaces)
        hosts = local.expand_targets(targets, self.opt.max_hosts)
        for gw in scan.gateways:
            if gw not in hosts:
                hosts.append(gw)
        self._prog("Netzwerk erkennen", 1, 1, f"{len(hosts)} Adressen in {len(targets)} Zielen")
        self._check()

        # UPnP parallel starten
        ssdp_result: dict[str, dict[str, str]] = {}
        ssdp_thread = None
        if self.opt.upnp:
            def _ssdp():
                try:
                    ssdp_result.update(ssdpmod.discover(3.0, [i.ip for i in ifaces] or None))
                except Exception:
                    pass
            ssdp_thread = threading.Thread(target=_ssdp, daemon=True)
            ssdp_thread.start()

        # ---- Phase 1: Erreichbarkeit ------------------------------------
        devices: dict[str, Device] = {}
        total = len(hosts)
        done = 0

        def probe(ip: str) -> Device | None:
            if self._stop.is_set():
                return None
            is_local = local.is_local(ip, ifaces)
            via: list[str] = []
            mac = ""
            if ip in own:
                via.append("self")
            if is_local and local.IS_WINDOWS:
                mac = arpmod.send_arp(ip)
                if mac:
                    via.append("arp")
            ok, rtt = pingmod.ping(ip, self.opt.ping_timeout_ms, allow_tcp=True)
            if ok:
                via.append("icmp")
            elif not mac and not is_local:
                ok2, rtt2 = pingmod.tcp_probe(ip, timeout=0.3)
                if ok2:
                    via.append("tcp")
                    rtt = rtt2
            if not via:
                return None
            d = Device(ip=ip, mac=mac, latency_ms=round(rtt, 1) if rtt is not None else None, alive_via=via)
            d.is_self = ip in own
            d.is_gateway = ip in scan.gateways
            d.subnet = local.subnet_of(ip, targets, ifaces)
            for i in ifaces:
                if i.cidr and ipaddress.IPv4Address(ip) in ipaddress.IPv4Network(i.cidr):
                    d.interface = i.name
                    if d.is_self:
                        d.mac = i.mac
                        d.netbios_name = socket.gethostname()
                    break
            return d

        with ThreadPoolExecutor(max_workers=self.opt.workers) as ex:
            futs = {ex.submit(probe, ip): ip for ip in hosts}
            for fut in as_completed(futs):
                done += 1
                if self._stop.is_set():
                    for f in futs:
                        f.cancel()
                    raise ScanCancelled()
                try:
                    d = fut.result()
                except Exception:
                    d = None
                if d is not None:
                    with self._lock:
                        devices[d.ip] = d
                    self._on_device(d)
                if done % 8 == 0 or done == total:
                    self._prog("Geräte suchen", done, total, f"{len(devices)} Geräte gefunden")
        self._check()

        # ---- Phase 2: MAC aus ARP-Tabelle ---------------------------------
        self._prog("MAC-Adressen", 0, 1, "ARP-Tabelle lesen")
        table = arpmod.arp_table()
        for ip, d in devices.items():
            if not d.mac and ip in table:
                d.mac = table[ip]
                if "arp" not in d.alive_via:
                    d.alive_via.append("arp")
        # Ziele, die nicht geantwortet haben, aber gerade in der ARP-Tabelle stehen: leben
        host_set = set(hosts)
        for ip, mac in table.items():
            if ip in host_set and ip not in devices and local.is_local(ip, ifaces):
                d = Device(ip=ip, mac=mac, alive_via=["arp"], subnet=local.subnet_of(ip, targets, ifaces))
                d.is_gateway = ip in scan.gateways
                devices[ip] = d
                self._on_device(d)
        for d in devices.values():
            d.vendor = oui.lookup(d.mac) if d.mac else ""
        self._prog("MAC-Adressen", 1, 1, "")
        self._check()

        # ---- Phase 3: UPnP-Ergebnis einarbeiten --------------------------
        if ssdp_thread is not None:
            ssdp_thread.join(timeout=4.0)
            locs: dict[str, str] = {}
            for ip, info in ssdp_result.items():
                if ip not in devices:
                    if local.is_local(ip, ifaces) or ip in hosts:
                        d = Device(ip=ip, alive_via=["ssdp"], subnet=local.subnet_of(ip, targets, ifaces))
                        d.is_gateway = ip in scan.gateways
                        d.mac = table.get(ip, "")
                        d.vendor = oui.lookup(d.mac) if d.mac else ""
                        devices[ip] = d
                        self._on_device(d)
                    else:
                        continue
                d = devices[ip]
                if "ssdp" not in d.alive_via:
                    d.alive_via.append("ssdp")
                d.ssdp_type = info.get("st", "")
                d.ssdp_location = info.get("location", "")
                if d.ssdp_location:
                    locs[ip] = d.ssdp_location
            if locs:
                self._prog("UPnP", 0, len(locs), "Gerätebeschreibungen lesen")
                with ThreadPoolExecutor(max_workers=16) as ex:
                    for n, (ip, info) in enumerate(zip(locs.keys(), ex.map(ssdpmod.describe, locs.values())), 1):
                        d = devices[ip]
                        d.ssdp_name = info.get("friendlyName", "")
                        model = " ".join(x for x in (info.get("manufacturer", ""), info.get("modelName", "")) if x)
                        d.ssdp_model = model
                        if info.get("deviceType"):
                            d.ssdp_type = info["deviceType"]
                        if info.get("presentationURL"):
                            d.admin_url = info["presentationURL"]
                        if not d.vendor and info.get("manufacturer"):
                            d.vendor = info["manufacturer"]
                        self._prog("UPnP", n, len(locs), d.ssdp_name or ip)
        self._check()

        # ---- Phase 4: Namen ---------------------------------------------
        alive = list(devices.values())
        if self.opt.resolve_names and alive:
            def resolve(d: Device) -> None:
                if self._stop.is_set():
                    return
                d.hostname = namesmod.clean_name(namesmod.reverse_dns(d.ip, 1.0))
                if self.opt.netbios:
                    d.netbios_name, _grp = namesmod.netbios_name(d.ip, 0.8)
                if self.opt.mdns:
                    d.mdns_name = namesmod.clean_name(namesmod.mdns_name(d.ip, 0.8))
            self._run_pool("Namen auflösen", alive, resolve, 48)
        self._check()

        # ---- Phase 5: Ports ---------------------------------------------
        if self.opt.port_mode != "none" and alive:
            plist = portsmod.QUICK_PORTS if self.opt.port_mode == "quick" else portsmod.FULL_PORTS

            def scan_p(d: Device) -> None:
                if self._stop.is_set():
                    return
                d.open_ports = portsmod.scan_ports(d.ip, plist, timeout=0.5, workers=24)
                d.services = {str(p): portsmod.service_name(p) for p in d.open_ports}
                if self.opt.http_titles:
                    for p in (80, 443, 8080, 8443, 5000, 5001, 8000, 8123, 8006, 9000):
                        if p in d.open_ports:
                            title, server = portsmod.http_title(d.ip, p, 2.0)
                            extra = " · ".join(x for x in (title, server) if x)
                            if extra:
                                d.services[str(p)] = f"{portsmod.service_name(p)}: {extra}"
                            break
                    if 22 in d.open_ports:
                        b = portsmod.banner(d.ip, 22, 1.5)
                        if b:
                            d.services["22"] = f"SSH: {b}"
            self._run_pool("Ports prüfen", alive, scan_p, 16)
        self._check()

        # ---- Phase 6: Klassifizieren --------------------------------------
        for d in alive:
            d.device_type = classify.classify(d)
            d.admin_url = classify.admin_url(d)
            d.last_seen = now_iso()
            d.first_seen = d.first_seen or d.last_seen
            self._on_device(d)

        # ---- Phase 7: Traceroute -------------------------------------------
        if self.opt.traceroute:
            self._prog("Pfade", 0, 1, "Weg ins Internet")
            try:
                scan.internet_path = tracemod.path_routers("1.1.1.1", 20, 800, self._stop.is_set, exclude=own)
            except Exception:
                scan.internet_path = []
            # fremde Subnetze: Pfad zu je einem Gerät
            seen_subnets: set[str] = set()
            trace_targets: list[Device] = []
            for d in alive:
                if d.is_self:
                    continue
                if self.opt.trace_all:
                    trace_targets.append(d)
                elif not local.is_local(d.ip, ifaces) and d.subnet not in seen_subnets:
                    seen_subnets.add(d.subnet)
                    trace_targets.append(d)
            if trace_targets:
                def tr(d: Device) -> None:
                    if self._stop.is_set():
                        return
                    try:
                        d.hops = tracemod.path_routers(d.ip, 16, 700, self._stop.is_set, exclude=own)
                    except Exception:
                        d.hops = []
                self._run_pool("Pfade", trace_targets, tr, 8)
                if not self.opt.trace_all:
                    # Gleiche Hops für alle Geräte desselben fremden Subnetzes übernehmen
                    by_subnet = {d.subnet: d.hops for d in trace_targets}
                    for d in alive:
                        if not d.hops and d.subnet in by_subnet and not local.is_local(d.ip, ifaces):
                            d.hops = list(by_subnet[d.subnet])
            # Router aus den Pfaden als Geräte aufnehmen
            for d in list(alive):
                for hop in d.hops:
                    if hop not in devices and _is_private(hop):
                        r = Device(ip=hop, alive_via=["trace"], device_type="router",
                                   subnet=local.subnet_of(hop, targets, ifaces), last_seen=now_iso())
                        r.first_seen = r.last_seen
                        r.mac = table.get(hop, "")
                        r.vendor = oui.lookup(r.mac) if r.mac else ""
                        devices[hop] = r
                        self._on_device(r)
            for hop in scan.internet_path:
                if hop not in devices and _is_private(hop):
                    r = Device(ip=hop, alive_via=["trace"], device_type="router",
                               subnet=local.subnet_of(hop, targets, ifaces), last_seen=now_iso())
                    r.first_seen = r.last_seen
                    r.mac = table.get(hop, "")
                    r.vendor = oui.lookup(r.mac) if r.mac else ""
                    devices[hop] = r
                    self._on_device(r)
        self._check()

        # ---- Phase 8: Internet ---------------------------------------------
        if self.opt.internet_check:
            self._prog("Internet", 0, 1, "DNS und Verbindung prüfen")
            scan.dns_ok, scan.internet_ok, scan.public_ip = internet_check()
            self._prog("Internet", 1, 1, "")

        scan.devices = sorted(devices.values(), key=lambda d: (d.subnet, d.ip_int()))
        scan.finished = now_iso()
        scan.duration_s = round(time.time() - t0, 1)
        scan.problems = diagnostics.analyze(scan)
        self._prog("Fertig", 1, 1, f"{len(scan.devices)} Geräte in {scan.duration_s:.0f} s")
        return scan

    # ------------------------------------------------------------------
    def _run_pool(self, phase: str, items: list, fn, workers: int) -> None:
        total = len(items)
        done = 0
        self._prog(phase, 0, total, "")
        with ThreadPoolExecutor(max_workers=max(1, min(workers, total))) as ex:
            futs = {ex.submit(fn, it): it for it in items}
            for fut in as_completed(futs):
                done += 1
                if self._stop.is_set():
                    for f in futs:
                        f.cancel()
                    raise ScanCancelled()
                try:
                    fut.result()
                except Exception:
                    pass
                it = futs[fut]
                self._prog(phase, done, total, getattr(it, "ip", ""))
                if isinstance(it, Device):
                    self._on_device(it)


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.IPv4Address(ip).is_private
    except ValueError:
        return False


def internet_check(timeout: float = 3.0) -> tuple[bool, bool, str]:
    """(DNS funktioniert, Internet erreichbar, öffentliche IP)."""
    dns_ok = False
    net_ok = False
    public_ip = ""
    try:
        socket.getaddrinfo("www.google.com", 443, proto=socket.IPPROTO_TCP)
        dns_ok = True
    except OSError:
        pass
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443)):
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            net_ok = True
            break
        except OSError:
            continue
    if net_ok and dns_ok:
        try:
            import urllib.request
            req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "NetGuard"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                public_ip = resp.read(64).decode("ascii", errors="ignore").strip()
        except Exception:
            public_ip = ""
    return dns_ok, net_ok, public_ip
