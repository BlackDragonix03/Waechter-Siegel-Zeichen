"""Minimaler SNMP-v2c-Client (GET / GETNEXT) für Schnittstellen-Zähler von Switches, NAS, Routern."""
from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field

OID_IF_DESCR = (1, 3, 6, 1, 2, 1, 2, 2, 1, 2)
OID_IF_IN = (1, 3, 6, 1, 2, 1, 2, 2, 1, 10)
OID_IF_OUT = (1, 3, 6, 1, 2, 1, 2, 2, 1, 16)
OID_IF_HC_IN = (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 6)
OID_IF_HC_OUT = (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 10)
OID_IF_NAME = (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 1)
OID_IF_OPER = (1, 3, 6, 1, 2, 1, 2, 2, 1, 8)
OID_SYS_DESCR = (1, 3, 6, 1, 2, 1, 1, 1, 0)
OID_SYS_NAME = (1, 3, 6, 1, 2, 1, 1, 5, 0)
OID_SYS_UPTIME = (1, 3, 6, 1, 2, 1, 1, 3, 0)


# ---- BER ---------------------------------------------------------------------
def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + _len(len(payload)) + payload


def _int(v: int) -> bytes:
    if v == 0:
        return _tlv(0x02, b"\x00")
    b = v.to_bytes((v.bit_length() + 8) // 8, "big", signed=True)
    return _tlv(0x02, b)


def _oid(oid: tuple[int, ...]) -> bytes:
    out = bytes([40 * oid[0] + oid[1]])
    for x in oid[2:]:
        if x < 0x80:
            out += bytes([x])
        else:
            parts = []
            while x:
                parts.append(x & 0x7F)
                x >>= 7
            out += bytes([p | 0x80 for p in reversed(parts[1:])]) + bytes([parts[0]])
    return _tlv(0x06, out)


def _read_tlv(data: bytes, pos: int) -> tuple[int, bytes, int]:
    tag = data[pos]
    pos += 1
    ln = data[pos]
    pos += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(data[pos:pos + n], "big")
        pos += n
    return tag, data[pos:pos + ln], pos + ln


def _dec_oid(b: bytes) -> tuple[int, ...]:
    out = [b[0] // 40, b[0] % 40]
    val = 0
    for x in b[1:]:
        val = (val << 7) | (x & 0x7F)
        if not x & 0x80:
            out.append(val)
            val = 0
    return tuple(out)


def _dec_value(tag: int, b: bytes):
    if tag in (0x02, 0x41, 0x42, 0x43, 0x46):   # INTEGER, Counter32, Gauge, TimeTicks, Counter64
        return int.from_bytes(b, "big", signed=(tag == 0x02))
    if tag == 0x04:
        return b.decode("utf-8", errors="replace")
    if tag == 0x06:
        return _dec_oid(b)
    if tag == 0x40:
        return ".".join(map(str, b))
    if tag in (0x80, 0x81, 0x82):               # noSuchObject / noSuchInstance / endOfMibView
        return None
    return b


def _request(ip: str, community: str, oids: list[tuple[int, ...]], pdu_tag: int, timeout: float, req_id: int) -> list[tuple[tuple[int, ...], object]]:
    varbinds = b"".join(_tlv(0x30, _oid(o) + _tlv(0x05, b"")) for o in oids)
    pdu = _tlv(pdu_tag, _int(req_id) + _int(0) + _int(0) + _tlv(0x30, varbinds))
    msg = _tlv(0x30, _int(1) + _tlv(0x04, community.encode()) + pdu)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(msg, (ip, 161))
        data, _ = s.recvfrom(65535)
    finally:
        s.close()
    _, body, _ = _read_tlv(data, 0)
    pos = 0
    _, _, pos = _read_tlv(body, pos)          # version
    _, _, pos = _read_tlv(body, pos)          # community
    ptag, pbody, _ = _read_tlv(body, pos)
    pos = 0
    _, _, pos = _read_tlv(pbody, pos)          # request id
    _, err, pos = _read_tlv(pbody, pos)
    if int.from_bytes(err, "big") != 0:
        raise RuntimeError(f"SNMP-Fehler {int.from_bytes(err, 'big')}")
    _, _, pos = _read_tlv(pbody, pos)
    _, vbl, _ = _read_tlv(pbody, pos)
    out = []
    pos = 0
    while pos < len(vbl):
        _, vb, pos = _read_tlv(vbl, pos)
        _, oidb, p2 = _read_tlv(vb, 0)
        vtag, vval, _ = _read_tlv(vb, p2)
        out.append((_dec_oid(oidb), _dec_value(vtag, vval)))
    return out


def snmp_get(ip: str, oids: list[tuple[int, ...]], community: str = "public", timeout: float = 2.0) -> dict[tuple[int, ...], object]:
    return dict(_request(ip, community, oids, 0xA0, timeout, int(time.time()) & 0x7FFF))


def snmp_walk(ip: str, base: tuple[int, ...], community: str = "public", timeout: float = 2.0, limit: int = 512) -> dict[tuple[int, ...], object]:
    out: dict[tuple[int, ...], object] = {}
    cur = base
    rid = int(time.time()) & 0x7FFF
    while len(out) < limit:
        rid += 1
        res = _request(ip, community, [cur], 0xA1, timeout, rid)
        if not res:
            break
        oid, val = res[0]
        if oid[:len(base)] != base or val is None or oid == cur:
            break
        out[oid] = val
        cur = oid
    return out


@dataclass
class SnmpInterface:
    index: int
    name: str
    in_octets: int | None = None
    out_octets: int | None = None
    up: bool | None = None


@dataclass
class SnmpResult:
    ok: bool = False
    error: str = ""
    sys_name: str = ""
    sys_descr: str = ""
    uptime_s: int | None = None
    interfaces: list[SnmpInterface] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


def query_interfaces(ip: str, community: str = "public", timeout: float = 2.0) -> SnmpResult:
    res = SnmpResult()
    try:
        sysinfo = snmp_get(ip, [OID_SYS_DESCR, OID_SYS_NAME, OID_SYS_UPTIME], community, timeout)
    except socket.timeout:
        res.error = "Keine SNMP-Antwort (Port 161). SNMP ist am Gerät vermutlich aus oder die Community stimmt nicht."
        return res
    except Exception as exc:
        res.error = f"SNMP-Fehler: {exc}"
        return res
    res.sys_descr = str(sysinfo.get(OID_SYS_DESCR, "") or "")
    res.sys_name = str(sysinfo.get(OID_SYS_NAME, "") or "")
    up = sysinfo.get(OID_SYS_UPTIME)
    res.uptime_s = int(up) // 100 if isinstance(up, int) else None
    try:
        descr = snmp_walk(ip, OID_IF_DESCR, community, timeout)
        names = snmp_walk(ip, OID_IF_NAME, community, timeout)
        hc_in = snmp_walk(ip, OID_IF_HC_IN, community, timeout)
        hc_out = snmp_walk(ip, OID_IF_HC_OUT, community, timeout) if hc_in else {}
        if not hc_in:
            hc_in = snmp_walk(ip, OID_IF_IN, community, timeout)
            hc_out = snmp_walk(ip, OID_IF_OUT, community, timeout)
        oper = snmp_walk(ip, OID_IF_OPER, community, timeout)
    except Exception as exc:
        res.error = f"Schnittstellen nicht lesbar: {exc}"
        res.ok = True
        return res
    for oid, d in descr.items():
        idx = oid[-1]
        name = str(names.get(OID_IF_NAME + (idx,), "") or d)
        i = SnmpInterface(index=idx, name=name)
        for table, attr in ((hc_in, "in_octets"), (hc_out, "out_octets")):
            for base in (OID_IF_HC_IN, OID_IF_IN, OID_IF_HC_OUT, OID_IF_OUT):
                v = table.get(base + (idx,))
                if isinstance(v, int):
                    setattr(i, attr, v)
                    break
        o = oper.get(OID_IF_OPER + (idx,))
        i.up = (o == 1) if isinstance(o, int) else None
        res.interfaces.append(i)
    res.ok = True
    return res
