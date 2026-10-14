"""MAC-Adressen: unter Windows per SendARP (ohne Admin), sonst aus der ARP-Tabelle."""
from __future__ import annotations

import ctypes
import re
import socket
import struct
import subprocess
import sys

from .local import subprocess_flags
from ..oui import normalize_mac

IS_WINDOWS = sys.platform.startswith("win")


def send_arp(ip: str, src_ip: str = "") -> str:
    """Fragt die MAC direkt per ARP ab (nur Windows, nur lokales Subnetz)."""
    if not IS_WINDOWS:
        return ""
    try:
        iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
        dest = struct.unpack("<L", socket.inet_aton(ip))[0]
        src = struct.unpack("<L", socket.inet_aton(src_ip))[0] if src_ip else 0
        mac = (ctypes.c_ubyte * 6)()
        length = ctypes.c_ulong(6)
        res = iphlpapi.SendARP(ctypes.c_ulong(dest), ctypes.c_ulong(src), ctypes.byref(mac), ctypes.byref(length))
        if res == 0 and length.value == 6:
            m = ":".join(f"{b:02x}" for b in mac)
            if m not in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
                return m
    except Exception:
        pass
    return ""


def arp_table() -> dict[str, str]:
    """Liest die ARP-/Nachbar-Tabelle des Systems: IP -> MAC."""
    table: dict[str, str] = {}
    if IS_WINDOWS:
        try:
            out = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10, **subprocess_flags()).stdout
        except (OSError, subprocess.SubprocessError):
            return table
        for line in out.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})", line)
            if m:
                mac = normalize_mac(m.group(2))
                if mac not in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
                    table[m.group(1)] = mac
        return table
    # Linux
    try:
        with open("/proc/net/arp") as fh:
            next(fh)
            for line in fh:
                parts = line.split()
                if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
                    table[parts[0]] = normalize_mac(parts[3])
        return table
    except OSError:
        pass
    try:
        out = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            m = re.search(r"^(\d+\.\d+\.\d+\.\d+).*lladdr\s+([0-9a-f:]{17})", line)
            if m:
                table[m.group(1)] = normalize_mac(m.group(2))
    except (OSError, subprocess.SubprocessError):
        pass
    try:  # macOS
        out = subprocess.run(["arp", "-an"], capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]{11,17})", line)
            if m:
                table[m.group(1)] = normalize_mac(m.group(2))
    except (OSError, subprocess.SubprocessError):
        pass
    return table
