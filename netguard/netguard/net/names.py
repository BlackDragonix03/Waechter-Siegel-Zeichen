"""Namensauflösung: Reverse-DNS, NetBIOS (Windows-Namen) und mDNS (Bonjour/Avahi)."""
from __future__ import annotations

import random
import socket
import struct


def reverse_dns(ip: str, timeout: float = 1.0) -> str:
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        name = socket.gethostbyaddr(ip)[0]
        if name and name != ip:
            return name
    except (socket.herror, socket.gaierror, OSError):
        pass
    finally:
        socket.setdefaulttimeout(old)
    return ""


# ---------------------------------------------------------------------------
# NetBIOS Node Status (UDP 137)
# ---------------------------------------------------------------------------
def netbios_name(ip: str, timeout: float = 1.0) -> tuple[str, str]:
    """Liefert (Computername, Arbeitsgruppe/Domäne) oder ("", "")."""
    tid = random.randint(0, 0xFFFF)
    # Header: ID, Flags 0x0000 (Query, nicht rekursiv), QD=1
    pkt = struct.pack("!HHHHHH", tid, 0x0000, 1, 0, 0, 0)
    pkt += b"\x20" + b"CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" + b"\x00"   # "*" kodiert
    pkt += struct.pack("!HH", 0x0021, 0x0001)                         # NBSTAT, IN
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(pkt, (ip, 137))
        data, _ = s.recvfrom(2048)
    except OSError:
        return "", ""
    finally:
        s.close()
    if len(data) < 57:
        return "", ""
    try:
        # Antwort: Header(12) + Name(34) + Typ/Klasse(4) + TTL(4) + RDLENGTH(2) + NUM_NAMES(1)
        pos = 12 + 34 + 4 + 4 + 2
        num = data[pos]
        pos += 1
        host = ""
        group = ""
        for _ in range(num):
            if pos + 18 > len(data):
                break
            raw = data[pos:pos + 15]
            suffix = data[pos + 15]
            flags = struct.unpack("!H", data[pos + 16:pos + 18])[0]
            pos += 18
            name = raw.decode("latin-1", errors="replace").rstrip(" \x00")
            is_group = bool(flags & 0x8000)
            if suffix == 0x00 and not is_group and not host:
                host = name
            elif suffix == 0x00 and is_group and not group:
                group = name
        return host, group
    except (IndexError, struct.error):
        return "", ""


# ---------------------------------------------------------------------------
# mDNS: PTR-Anfrage für x.x.x.x.in-addr.arpa an 224.0.0.251:5353
# ---------------------------------------------------------------------------
def _encode_name(name: str) -> bytes:
    out = b""
    for part in name.strip(".").split("."):
        out += bytes([len(part)]) + part.encode("ascii", errors="ignore")
    return out + b"\x00"


def _decode_name(data: bytes, pos: int) -> tuple[str, int]:
    labels: list[str] = []
    jumped = False
    end = pos
    guard = 0
    while guard < 128:
        guard += 1
        if pos >= len(data):
            break
        length = data[pos]
        if length == 0:
            pos += 1
            break
        if length & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", data[pos:pos + 2])[0] & 0x3FFF
            if not jumped:
                end = pos + 2
            jumped = True
            pos = ptr
            continue
        pos += 1
        labels.append(data[pos:pos + length].decode("utf-8", errors="replace"))
        pos += length
    if not jumped:
        end = pos
    return ".".join(labels), end


def mdns_name(ip: str, timeout: float = 1.0) -> str:
    """Fragt den mDNS-Namen eines Geräts ab (Antwort per Unicast)."""
    rev = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
    tid = 0
    pkt = struct.pack("!HHHHHH", tid, 0x0000, 1, 0, 0, 0)
    pkt += _encode_name(rev) + struct.pack("!HH", 12, 0x8001)   # PTR, IN + Unicast-Response-Bit
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        # direkt an das Gerät UND an die Multicast-Gruppe
        try:
            s.sendto(pkt, (ip, 5353))
        except OSError:
            pass
        s.sendto(pkt, ("224.0.0.251", 5353))
        deadline_tries = 3
        while deadline_tries:
            deadline_tries -= 1
            data, addr = s.recvfrom(4096)
            name = _parse_ptr(data, rev)
            if name:
                return name.rstrip(".")
    except OSError:
        pass
    finally:
        s.close()
    return ""


def _parse_ptr(data: bytes, want: str) -> str:
    try:
        _, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", data[:12])
        pos = 12
        for _ in range(qd):
            _, pos = _decode_name(data, pos)
            pos += 4
        for _ in range(an + ns + ar):
            name, pos = _decode_name(data, pos)
            typ, cls, ttl, rdlen = struct.unpack("!HHIH", data[pos:pos + 10])
            pos += 10
            if typ == 12 and name.lower() == want.lower():
                target, _ = _decode_name(data, pos)
                return target
            pos += rdlen
    except (struct.error, IndexError):
        pass
    return ""


def clean_name(name: str) -> str:
    """Kürzt ".local" / ".fritz.box" usw. nicht weg, entfernt aber Müll."""
    name = (name or "").strip().rstrip(".")
    if name.lower().endswith(".local"):
        name = name[:-6]
    return name
