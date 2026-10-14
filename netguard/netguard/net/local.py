"""Lokale Netzwerkschnittstellen, Gateways und Subnetze ermitteln."""
from __future__ import annotations

import ctypes
import ipaddress
import re
import socket
import struct
import subprocess
import sys
from typing import Iterable

from ..model import InterfaceInfo

IS_WINDOWS = sys.platform.startswith("win")


def subprocess_flags() -> dict:
    """Verhindert Konsolenfenster unter Windows (bei --windowed Exe)."""
    if IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def _cidr(ip: str, mask: str) -> str:
    try:
        net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
        return str(net)
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Windows: GetAdaptersInfo (iphlpapi), ohne Admin, sprachunabhängig
# ---------------------------------------------------------------------------
def _win_interfaces() -> list[InterfaceInfo]:
    MAX_ADAPTER_NAME_LENGTH = 256
    MAX_ADAPTER_DESCRIPTION_LENGTH = 128
    MAX_ADAPTER_ADDRESS_LENGTH = 8

    class IP_ADDRESS_STRING(ctypes.Structure):
        _fields_ = [("String", ctypes.c_char * 16)]

    class IP_ADDR_STRING(ctypes.Structure):
        pass

    IP_ADDR_STRING._fields_ = [
        ("Next", ctypes.POINTER(IP_ADDR_STRING)),
        ("IpAddress", IP_ADDRESS_STRING),
        ("IpMask", IP_ADDRESS_STRING),
        ("Context", ctypes.c_ulong),
    ]

    class IP_ADAPTER_INFO(ctypes.Structure):
        pass

    IP_ADAPTER_INFO._fields_ = [
        ("Next", ctypes.POINTER(IP_ADAPTER_INFO)),
        ("ComboIndex", ctypes.c_ulong),
        ("AdapterName", ctypes.c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
        ("Description", ctypes.c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
        ("AddressLength", ctypes.c_uint),
        ("Address", ctypes.c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
        ("Index", ctypes.c_ulong),
        ("Type", ctypes.c_uint),
        ("DhcpEnabled", ctypes.c_uint),
        ("CurrentIpAddress", ctypes.POINTER(IP_ADDR_STRING)),
        ("IpAddressList", IP_ADDR_STRING),
        ("GatewayList", IP_ADDR_STRING),
        ("DhcpServer", IP_ADDR_STRING),
        ("HaveWins", ctypes.c_int),
        ("PrimaryWinsServer", IP_ADDR_STRING),
        ("SecondaryWinsServer", IP_ADDR_STRING),
        ("LeaseObtained", ctypes.c_ulonglong),
        ("LeaseExpires", ctypes.c_ulonglong),
    ]

    iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
    size = ctypes.c_ulong(0)
    iphlpapi.GetAdaptersInfo(None, ctypes.byref(size))
    if size.value == 0:
        return []
    buf = ctypes.create_string_buffer(size.value)
    if iphlpapi.GetAdaptersInfo(buf, ctypes.byref(size)) != 0:
        return []

    result: list[InterfaceInfo] = []
    p = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_INFO))
    while p:
        a = p.contents
        desc = a.Description.decode("mbcs", errors="replace")
        mac = ":".join(f"{a.Address[i]:02x}" for i in range(a.AddressLength)) if a.AddressLength else ""
        gw = a.GatewayList.IpAddress.String.decode("ascii", errors="replace")
        if gw == "0.0.0.0":
            gw = ""
        node = ctypes.pointer(a.IpAddressList)
        while node:
            ip = node.contents.IpAddress.String.decode("ascii", errors="replace")
            mask = node.contents.IpMask.String.decode("ascii", errors="replace")
            if ip and ip != "0.0.0.0":
                result.append(InterfaceInfo(name=desc, ip=ip, netmask=mask, gateway=gw, mac=mac, cidr=_cidr(ip, mask)))
            node = node.contents.Next
        p = a.Next
    # DNS-Server über ipconfig wäre sprachabhängig; wir nutzen GetNetworkParams
    try:
        dns = _win_dns_servers()
        for r in result:
            r.dns = dns
    except Exception:
        pass
    return result


def _win_dns_servers() -> list[str]:
    class IP_ADDRESS_STRING(ctypes.Structure):
        _fields_ = [("String", ctypes.c_char * 16)]

    class IP_ADDR_STRING(ctypes.Structure):
        pass

    IP_ADDR_STRING._fields_ = [
        ("Next", ctypes.POINTER(IP_ADDR_STRING)),
        ("IpAddress", IP_ADDRESS_STRING),
        ("IpMask", IP_ADDRESS_STRING),
        ("Context", ctypes.c_ulong),
    ]

    class FIXED_INFO(ctypes.Structure):
        _fields_ = [
            ("HostName", ctypes.c_char * 132),
            ("DomainName", ctypes.c_char * 132),
            ("CurrentDnsServer", ctypes.POINTER(IP_ADDR_STRING)),
            ("DnsServerList", IP_ADDR_STRING),
            ("NodeType", ctypes.c_uint),
            ("ScopeId", ctypes.c_char * 260),
            ("EnableRouting", ctypes.c_uint),
            ("EnableProxy", ctypes.c_uint),
            ("EnableDns", ctypes.c_uint),
        ]

    iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]
    size = ctypes.c_ulong(0)
    iphlpapi.GetNetworkParams(None, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    if iphlpapi.GetNetworkParams(buf, ctypes.byref(size)) != 0:
        return []
    info = ctypes.cast(buf, ctypes.POINTER(FIXED_INFO)).contents
    out: list[str] = []
    node = ctypes.pointer(info.DnsServerList)
    while node:
        ip = node.contents.IpAddress.String.decode("ascii", errors="replace")
        if ip and ip != "0.0.0.0":
            out.append(ip)
        node = node.contents.Next
    return out


# ---------------------------------------------------------------------------
# Linux / macOS
# ---------------------------------------------------------------------------
def _linux_interfaces() -> list[InterfaceInfo]:
    gateways: dict[str, str] = {}
    default_gw = ""
    try:
        with open("/proc/net/route") as fh:
            next(fh)
            for line in fh:
                parts = line.split()
                if len(parts) < 8:
                    continue
                iface, dest, gw, flags = parts[0], parts[1], parts[2], int(parts[3], 16)
                if dest == "00000000" and flags & 2:
                    gw_ip = socket.inet_ntoa(struct.pack("<L", int(gw, 16)))
                    gateways[iface] = gw_ip
                    default_gw = default_gw or gw_ip
    except OSError:
        pass

    result: list[InterfaceInfo] = []
    try:
        out = subprocess.run(["ip", "-o", "-4", "addr"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            m = re.search(r"^\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
            if not m:
                continue
            name, ip, bits = m.group(1), m.group(2), int(m.group(3))
            if name == "lo":
                continue
            mask = str(ipaddress.IPv4Network(f"0.0.0.0/{bits}").netmask)
            result.append(InterfaceInfo(name=name, ip=ip, netmask=mask, gateway=gateways.get(name, ""),
                                        mac=_linux_mac(name), cidr=_cidr(ip, mask)))
    except (OSError, subprocess.SubprocessError):
        pass
    if not result:
        # Notlösung ohne "ip": nur die IP der Standardroute
        ip = _primary_ip()
        if ip:
            mask = "255.255.255.0"
            iface = next(iter(gateways), "")
            result.append(InterfaceInfo(name=iface or "default", ip=ip, netmask=mask, gateway=default_gw,
                                        mac=_linux_mac(iface) if iface else "", cidr=_cidr(ip, mask)))
    dns = _linux_dns()
    for r in result:
        r.dns = dns
    return result


def _linux_mac(name: str) -> str:
    try:
        with open(f"/sys/class/net/{name}/address") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _linux_dns() -> list[str]:
    out: list[str] = []
    try:
        with open("/etc/resolv.conf") as fh:
            for line in fh:
                if line.startswith("nameserver"):
                    out.append(line.split()[1])
    except OSError:
        pass
    return out


def _primary_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


# ---------------------------------------------------------------------------
def interfaces() -> list[InterfaceInfo]:
    """Alle IPv4-Schnittstellen mit Adresse (ohne Loopback, ohne APIPA-Filter)."""
    try:
        res = _win_interfaces() if IS_WINDOWS else _linux_interfaces()
    except Exception:
        res = []
    return [r for r in res if r.ip and not r.ip.startswith("127.")]


def gateways(ifaces: Iterable[InterfaceInfo]) -> list[str]:
    out: list[str] = []
    for i in ifaces:
        if i.gateway and i.gateway not in out:
            out.append(i.gateway)
    return out


def default_targets(ifaces: Iterable[InterfaceInfo]) -> list[str]:
    """Sinnvolle Standardziele: Subnetze der aktiven Schnittstellen (max. /22)."""
    out: list[str] = []
    for i in ifaces:
        if not i.cidr or i.ip.startswith("169.254."):
            continue
        net = ipaddress.IPv4Network(i.cidr)
        if net.prefixlen < 22:
            net = ipaddress.IPv4Network(f"{i.ip}/22", strict=False)
        s = str(net)
        if s not in out:
            out.append(s)
    return out


def own_ips(ifaces: Iterable[InterfaceInfo]) -> set[str]:
    return {i.ip for i in ifaces}


def expand_targets(targets: Iterable[str], limit: int = 4096) -> list[str]:
    """Wandelt CIDR / Bereiche / Einzel-IPs in eine Liste von Hosts um."""
    hosts: list[str] = []
    seen: set[str] = set()
    for t in targets:
        t = t.strip()
        if not t:
            continue
        try:
            if "-" in t and "/" not in t:
                a, b = t.split("-", 1)
                a = a.strip()
                b = b.strip()
                start = ipaddress.IPv4Address(a)
                if "." not in b:
                    b = ".".join(a.split(".")[:3] + [b])
                end = ipaddress.IPv4Address(b)
                cur = int(start)
                while cur <= int(end) and len(hosts) < limit:
                    ip = str(ipaddress.IPv4Address(cur))
                    if ip not in seen:
                        seen.add(ip)
                        hosts.append(ip)
                    cur += 1
            elif "/" in t:
                net = ipaddress.IPv4Network(t, strict=False)
                it = net.hosts() if net.prefixlen < 31 else iter(net)
                for h in it:
                    if len(hosts) >= limit:
                        break
                    ip = str(h)
                    if ip not in seen:
                        seen.add(ip)
                        hosts.append(ip)
            else:
                ip = str(ipaddress.IPv4Address(t))
                if ip not in seen:
                    seen.add(ip)
                    hosts.append(ip)
        except ValueError:
            continue
    return hosts


def subnet_of(ip: str, targets: Iterable[str], ifaces: Iterable[InterfaceInfo]) -> str:
    """Welchem Ziel-Subnetz gehört die IP an?"""
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return ""
    for i in ifaces:
        if i.cidr and addr in ipaddress.IPv4Network(i.cidr):
            return i.cidr
    for t in targets:
        try:
            if "/" in t and addr in ipaddress.IPv4Network(t, strict=False):
                return str(ipaddress.IPv4Network(t, strict=False))
        except ValueError:
            continue
    return str(ipaddress.IPv4Network(f"{ip}/24", strict=False))


def is_local(ip: str, ifaces: Iterable[InterfaceInfo]) -> bool:
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return any(i.cidr and addr in ipaddress.IPv4Network(i.cidr) for i in ifaces)
