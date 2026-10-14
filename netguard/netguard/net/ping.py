"""ICMP-Ping: unter Windows über IcmpSendEcho (ohne Admin, ohne Konsolenfenster),
sonst über das ping-Programm; als letzte Möglichkeit ein TCP-Verbindungsversuch."""
from __future__ import annotations

import ctypes
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

from .local import subprocess_flags

IS_WINDOWS = sys.platform.startswith("win")

_icmp_lock = threading.Lock()
_icmp_handle = None
_icmp_broken = False


def _win_icmp_handle():
    global _icmp_handle, _icmp_broken
    with _icmp_lock:
        if _icmp_handle is None and not _icmp_broken:
            try:
                iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
                iphlpapi.IcmpCreateFile.restype = ctypes.c_void_p
                h = iphlpapi.IcmpCreateFile()
                if h in (None, 0, ctypes.c_void_p(-1).value):
                    _icmp_broken = True
                else:
                    _icmp_handle = h
            except Exception:
                _icmp_broken = True
        return _icmp_handle


class _ICMP_ECHO_REPLY(ctypes.Structure):
    _fields_ = [
        ("Address", ctypes.c_ulong),
        ("Status", ctypes.c_ulong),
        ("RoundTripTime", ctypes.c_ulong),
        ("DataSize", ctypes.c_ushort),
        ("Reserved", ctypes.c_ushort),
        ("Data", ctypes.c_void_p),
        ("Options", ctypes.c_ubyte * 8),
    ]


def _win_ping(ip: str, timeout_ms: int, ttl: int | None = None) -> tuple[bool, float | None, str]:
    """Rückgabe: (antwortet, Laufzeit ms, Antwort-Adresse).

    Mit ttl wird die Adresse des Routers zurückgegeben, der "TTL abgelaufen" meldet
    (für Traceroute)."""
    h = _win_icmp_handle()
    if h is None:
        raise OSError("ICMP nicht verfügbar")
    iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
    iphlpapi.IcmpSendEcho.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ushort,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
    iphlpapi.IcmpSendEcho.restype = ctypes.c_ulong
    dest = struct.unpack("<L", socket.inet_aton(ip))[0]
    data = b"NetGuard"
    reply_size = ctypes.sizeof(_ICMP_ECHO_REPLY) + len(data) + 8
    reply = ctypes.create_string_buffer(reply_size)
    options = None
    if ttl is not None:
        class IP_OPTION_INFORMATION(ctypes.Structure):
            _fields_ = [("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte),
                        ("OptionsSize", ctypes.c_ubyte), ("OptionsData", ctypes.c_void_p)]
        opt = IP_OPTION_INFORMATION(ttl, 0, 0, 0, None)
        options = ctypes.byref(opt)
    n = iphlpapi.IcmpSendEcho(h, dest, data, len(data), options, reply, reply_size, timeout_ms)
    if n == 0:
        return False, None, ""
    r = ctypes.cast(reply, ctypes.POINTER(_ICMP_ECHO_REPLY)).contents
    addr = socket.inet_ntoa(struct.pack("<L", r.Address))
    if r.Status == 0:
        return True, float(r.RoundTripTime), addr
    # 11013 = IP_TTL_EXPIRED_TRANSIT, 11002 = DEST_NET_UNREACHABLE ...
    if r.Status == 11013:
        return False, float(r.RoundTripTime), addr
    return False, None, addr if r.Status in (11002, 11003, 11004, 11005) else ""


_PING_BIN = shutil.which("ping")


def _cli_ping(ip: str, timeout_ms: int) -> tuple[bool, float | None]:
    if not _PING_BIN:
        raise OSError("ping-Programm fehlt")
    if IS_WINDOWS:
        cmd = [_PING_BIN, "-n", "1", "-w", str(timeout_ms), ip]
    elif sys.platform == "darwin":
        cmd = [_PING_BIN, "-c", "1", "-W", str(timeout_ms), ip]
    else:
        cmd = [_PING_BIN, "-c", "1", "-W", str(max(1, round(timeout_ms / 1000))), ip]
    try:
        t0 = time.perf_counter()
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_ms / 1000 + 2, **subprocess_flags())
        dt = (time.perf_counter() - t0) * 1000
    except subprocess.SubprocessError:
        return False, None
    out = p.stdout
    # Windows antwortet auch bei "Zielhost nicht erreichbar" mit Exit 0
    if p.returncode != 0 or re.search(r"nicht erreichbar|unreachable|Zeit.berschreitung|timed out|100% (?:Verlust|packet loss)", out, re.I):
        return False, None
    m = re.search(r"(?:Zeit|time)[=<]\s*([\d.,]+)\s*ms", out, re.I)
    if m:
        try:
            return True, float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return (p.returncode == 0), dt


def tcp_probe(ip: str, ports=(80, 443, 22, 445, 139, 135, 8080, 53, 62078, 7, 23), timeout: float = 0.4) -> tuple[bool, float | None]:
    """Host gilt als erreichbar, wenn ein Port antwortet (offen ODER aktiv abgelehnt)."""
    for port in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            err = s.connect_ex((ip, port))
        except OSError:
            err = -1
        finally:
            s.close()
        dt = (time.perf_counter() - t0) * 1000
        if err == 0:
            return True, dt
        # ECONNREFUSED: Host lebt, Port zu (Linux 111, Windows 10061)
        if err in (111, 10061, 61):
            return True, dt
    return False, None


def ping(ip: str, timeout_ms: int = 600, allow_tcp: bool = True) -> tuple[bool, float | None]:
    """Erreichbarkeits-Test. Rückgabe (erreichbar, Laufzeit in ms)."""
    if IS_WINDOWS:
        try:
            ok, rtt, _ = _win_ping(ip, timeout_ms)
            if ok:
                return True, rtt
            return False, None
        except OSError:
            pass
    try:
        return _cli_ping(ip, timeout_ms)
    except OSError:
        pass
    if allow_tcp:
        return tcp_probe(ip)
    return False, None


def ping_ttl(ip: str, ttl: int, timeout_ms: int = 1000) -> tuple[bool, str, float | None]:
    """Ein Traceroute-Schritt: (Ziel erreicht?, antwortende Adresse, Laufzeit).

    Eine Adresse mit negativer Laufzeit bedeutet "Ziel unerreichbar" (Ende des Pfads)."""
    if IS_WINDOWS:
        try:
            ok, rtt, addr = _win_ping(ip, timeout_ms, ttl=ttl)
            if not ok and rtt is None and addr:
                return False, addr, -1.0
            return ok, addr, rtt
        except OSError:
            return False, "", None
    # Linux: ICMP-Socket mit TTL (Linux erlaubt SOCK_DGRAM/ICMP ohne root, wenn
    # net.ipv4.ping_group_range es zulässt; sonst UDP-Traceroute)
    try:
        return _linux_ttl_probe(ip, ttl, timeout_ms)
    except OSError:
        return False, "", None


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return (~s) & 0xFFFF


def _linux_ttl_probe(ip: str, ttl: int, timeout_ms: int) -> tuple[bool, str, float | None]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        raw = True
    except PermissionError:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP)
        raw = False
    sock.settimeout(timeout_ms / 1000)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
    ident = threading.get_ident() & 0xFFFF
    header = struct.pack("!BBHHH", 8, 0, 0, ident, ttl)
    payload = b"NetGuard"
    chk = _checksum(header + payload)
    pkt = struct.pack("!BBHHH", 8, 0, chk, ident, ttl) + payload
    t0 = time.perf_counter()
    try:
        sock.sendto(pkt, (ip, 0))
        while True:
            data, addr = sock.recvfrom(1024)
            dt = (time.perf_counter() - t0) * 1000
            icmp = data[20:] if raw else data
            if len(icmp) < 8:
                continue
            typ = icmp[0]
            if typ == 0:
                return True, addr[0], dt
            if typ == 11:
                return False, addr[0], dt
            if typ == 3:
                return False, addr[0], -1.0
    except socket.timeout:
        return False, "", None
    finally:
        sock.close()
