"""Subnetz-Suche: findet Subnetze im Heimnetz, ohne dass sie angegeben werden müssen.

Für jedes mögliche /24 der privaten Bereiche werden nur typische Router-/Gateway-Adressen
(.1, .254, .2) angepingt. Antwortet eine, gilt das Subnetz als gefunden und wird komplett
gescannt. Zusätzlich fließen Hinweise ein: Routing-Tabelle, ARP-Tabelle, Traceroute-Hops.
"""
from __future__ import annotations

import ctypes
import ipaddress
import socket
import struct
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable

from . import ping as pingmod, arp as arpmod

IS_WINDOWS = sys.platform.startswith("win")

PROBE_HOSTS_QUICK = (1, 254, 2)
PROBE_HOSTS_FULL = (1, 254)


def _net(ip: str, prefix: int = 24) -> str:
    return str(ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False))


# ---------------------------------------------------------------------------
# Routing-Tabelle (bekannte Netze sind der beste Hinweis)
# ---------------------------------------------------------------------------
def route_networks() -> list[str]:
    """Alle Netze aus der Routing-Tabelle (ohne Standardroute, Loopback, Multicast, Host-Routen)."""
    nets: list[str] = []
    try:
        rows = _win_routes() if IS_WINDOWS else _linux_routes()
    except Exception:
        rows = []
    for dest, mask in rows:
        try:
            n = ipaddress.IPv4Network(f"{dest}/{mask}", strict=False)
        except ValueError:
            continue
        if n.prefixlen == 0 or n.prefixlen >= 31 or n.is_loopback or n.is_multicast or n.is_link_local or n.is_reserved:
            continue
        if not n.is_private:
            continue
        s = str(n)
        if s not in nets:
            nets.append(s)
    return nets


def _win_routes() -> list[tuple[str, str]]:
    class MIB_IPFORWARDROW(ctypes.Structure):
        _fields_ = [("dwForwardDest", ctypes.c_ulong), ("dwForwardMask", ctypes.c_ulong), ("dwForwardPolicy", ctypes.c_ulong),
                    ("dwForwardNextHop", ctypes.c_ulong), ("dwForwardIfIndex", ctypes.c_ulong), ("dwForwardType", ctypes.c_ulong),
                    ("dwForwardProto", ctypes.c_ulong), ("dwForwardAge", ctypes.c_ulong), ("dwForwardNextHopAS", ctypes.c_ulong),
                    ("dwForwardMetric1", ctypes.c_ulong), ("dwForwardMetric2", ctypes.c_ulong), ("dwForwardMetric3", ctypes.c_ulong),
                    ("dwForwardMetric4", ctypes.c_ulong), ("dwForwardMetric5", ctypes.c_ulong)]

    iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
    size = ctypes.c_ulong(0)
    iphlpapi.GetIpForwardTable(None, ctypes.byref(size), 0)
    buf = ctypes.create_string_buffer(size.value)
    if iphlpapi.GetIpForwardTable(buf, ctypes.byref(size), 0) != 0:
        return []
    count = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ulong)).contents.value
    rows = ctypes.cast(ctypes.addressof(buf) + ctypes.sizeof(ctypes.c_ulong), ctypes.POINTER(MIB_IPFORWARDROW * count)).contents
    out = []
    for r in rows:
        out.append((socket.inet_ntoa(struct.pack("<L", r.dwForwardDest)), socket.inet_ntoa(struct.pack("<L", r.dwForwardMask))))
    return out


def _linux_routes() -> list[tuple[str, str]]:
    out = []
    with open("/proc/net/route") as fh:
        next(fh)
        for line in fh:
            parts = line.split()
            if len(parts) < 8:
                continue
            out.append((socket.inet_ntoa(struct.pack("<L", int(parts[1], 16))), socket.inet_ntoa(struct.pack("<L", int(parts[7], 16)))))
    return out


# ---------------------------------------------------------------------------
# Kandidaten
# ---------------------------------------------------------------------------
def candidate_subnets(mode: str, hints: Iterable[str] = (), exclude: Iterable[str] = ()) -> list[str]:
    """Liste von /24-Netzen, die geprüft werden. Hinweise zuerst, dann nach Wahrscheinlichkeit.

    mode: "quick" (alle 192.168.*, alle 172.16-31.*, gängige 10er-Netze) oder
          "full"  (zusätzlich 10.0.0.0/8 komplett, 65536 Netze).
    """
    seen: set[str] = set(exclude)
    out: list[str] = []

    def add(net: str) -> None:
        if net not in seen:
            seen.add(net)
            out.append(net)

    for h in hints:
        try:
            n = ipaddress.IPv4Network(h, strict=False)
        except ValueError:
            continue
        if n.prefixlen >= 24:
            add(_net(str(n.network_address)))
        else:
            # größere Netze: alle enthaltenen /24 (begrenzt)
            for i, sub in enumerate(n.subnets(new_prefix=24)):
                if i >= 4096:
                    break
                add(str(sub))
    # 192.168.0.0/16: alle 256
    for c in list(range(0, 2)) + [178, 100, 10, 50, 2, 3, 4, 5, 8, 20, 30, 88, 99, 123, 200, 254, 255] + list(range(2, 256)):
        add(f"192.168.{c}.0/24")
    # 10.x: gängige Muster zuerst
    for b in (0, 1, 10, 100, 8, 20, 42, 50, 99, 200, 254):
        for c in range(0, 256):
            add(f"10.{b}.{c}.0/24")
    for b in range(0, 256):
        add(f"10.{b}.0.0/24")
        add(f"10.{b}.1.0/24")
        add(f"10.{b}.{b}.0/24")
    # 172.16.0.0/12: alle 4096
    for b in range(16, 32):
        for c in range(0, 256):
            add(f"172.{b}.{c}.0/24")
    if mode == "full":
        for b in range(0, 256):
            for c in range(0, 256):
                add(f"10.{b}.{c}.0/24")
    return out


# ---------------------------------------------------------------------------
# Suche
# ---------------------------------------------------------------------------
def probe_subnets(candidates: list[str], timeout_ms: int = 350, workers: int = 256, probe_hosts=PROBE_HOSTS_QUICK,
                  progress: Callable[[int, int, str], None] | None = None, stop: Callable[[], bool] | None = None,
                  known_alive: Iterable[str] = ()) -> dict[str, list[str]]:
    """Prüft Kandidaten. Rückgabe: gefundenes Subnetz -> antwortende Adressen."""
    found: dict[str, list[str]] = {}
    for ip in known_alive:
        found.setdefault(_net(ip), []).append(ip)
    targets: list[tuple[str, str]] = []
    for net in candidates:
        base = net.split("/")[0].rsplit(".", 1)[0]
        for h in probe_hosts:
            targets.append((net, f"{base}.{h}"))
    total = len(targets)
    done = 0
    cb = progress or (lambda d, t, m: None)
    cb(0, total, f"{len(candidates)} mögliche Subnetze")

    def probe(item: tuple[str, str]) -> tuple[str, str, bool]:
        net, ip = item
        if stop is not None and stop():
            return net, ip, False
        ok, _ = pingmod.ping(ip, timeout_ms, allow_tcp=False)
        return net, ip, ok

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(probe, t) for t in targets]
        for fut in as_completed(futs):
            done += 1
            if stop is not None and stop():
                for f in futs:
                    f.cancel()
                break
            try:
                net, ip, ok = fut.result()
            except Exception:
                continue
            if ok:
                lst = found.setdefault(net, [])
                if ip not in lst:
                    lst.append(ip)
            if done % 64 == 0 or done == total:
                cb(done, total, f"{len(found)} Subnetze gefunden" + (": " + ", ".join(sorted(found)[:6]) + (" …" if len(found) > 6 else "") if found else ""))
    return found


def arp_hint_networks() -> list[str]:
    """Netze von Adressen in der ARP-Tabelle (zeigen oft andere Subnetze am selben Kabel)."""
    out: list[str] = []
    for ip in arpmod.arp_table():
        try:
            if ipaddress.IPv4Address(ip).is_private:
                n = _net(ip)
                if n not in out:
                    out.append(n)
        except ValueError:
            continue
    return out
