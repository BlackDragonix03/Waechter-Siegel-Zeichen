"""UPnP/SSDP-Suche: findet Router, Fernseher, Lautsprecher, NAS usw. samt Namen."""
from __future__ import annotations

import re
import socket
import time
import urllib.request
import xml.etree.ElementTree as ET

MSEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1900\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 2\r\n"
    "ST: ssdp:all\r\n\r\n"
).encode()


def discover(timeout: float = 3.0, bind_ips: list[str] | None = None) -> dict[str, dict[str, str]]:
    """Rückgabe: IP -> {location, st, server, usn}."""
    found: dict[str, dict[str, str]] = {}
    socks: list[socket.socket] = []
    for bind in (bind_ips or [""]):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            if bind:
                s.bind((bind, 0))
                try:
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(bind))
                except OSError:
                    pass
            s.settimeout(0.3)
            for _ in range(2):
                s.sendto(MSEARCH, ("239.255.255.250", 1900))
            socks.append(s)
        except OSError:
            continue
    deadline = time.time() + timeout
    while time.time() < deadline and socks:
        for s in socks:
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                continue
            ip = addr[0]
            headers = _parse_headers(data)
            entry = found.setdefault(ip, {})
            for key in ("location", "st", "server", "usn"):
                if headers.get(key) and not entry.get(key):
                    entry[key] = headers[key]
            # Router-Beschreibung bevorzugen
            if "InternetGatewayDevice" in headers.get("st", ""):
                entry["location"] = headers.get("location", entry.get("location", ""))
                entry["st"] = headers["st"]
    for s in socks:
        s.close()
    return found


def _parse_headers(data: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in data.decode("utf-8", errors="replace").split("\r\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def describe(location: str, timeout: float = 3.0) -> dict[str, str]:
    """Liest die UPnP-Gerätebeschreibung (XML): friendlyName, modelName, manufacturer, deviceType, presentationURL."""
    info: dict[str, str] = {}
    if not location.lower().startswith("http"):
        return info
    try:
        req = urllib.request.Request(location, headers={"User-Agent": "NetGuard"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(200_000)
    except Exception:
        return info
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return info
    ns_strip = lambda tag: tag.split("}", 1)[-1]  # noqa: E731
    device = None
    for el in root.iter():
        if ns_strip(el.tag) == "device":
            device = el
            break
    if device is None:
        return info
    for el in device:
        tag = ns_strip(el.tag)
        if tag in ("friendlyName", "modelName", "manufacturer", "deviceType", "presentationURL",
                   "modelDescription", "modelNumber", "serialNumber"):
            info[tag] = (el.text or "").strip()
    if info.get("presentationURL") and not info["presentationURL"].lower().startswith("http"):
        m = re.match(r"^(https?://[^/]+)", location)
        if m:
            info["presentationURL"] = m.group(1) + "/" + info["presentationURL"].lstrip("/")
    return info
