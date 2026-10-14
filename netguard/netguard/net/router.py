"""Router abfragen: UPnP-IGD (ohne Login, alle Router) und TR-064 (Fritz!Box, mit Login).

UPnP-IGD liefert die WAN-Zähler (gesamt gesendet/empfangen), aktuelle Raten, Uptime und
die externe IP. TR-064 liefert die Geräteliste des Routers mit "aktiv", Anschlussart,
Link-Geschwindigkeit und (Mesh) Signalstärke.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from . import ssdp as ssdpmod

SOAP_ENV = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
    '<u:{action} xmlns:u="{service}">{args}</u:{action}></s:Body></s:Envelope>'
)


def _strip(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _get(url: str, timeout: float = 4.0, opener=None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "NetGuard"})
    op = opener or urllib.request.build_opener()
    with op.open(req, timeout=timeout) as resp:
        return resp.read(2_000_000)


def soap_call(control_url: str, service: str, action: str, args: dict[str, str] | None = None,
              timeout: float = 5.0, opener=None) -> dict[str, str]:
    """Führt eine SOAP-Aktion aus und liefert die Antwortfelder (ohne 'New'-Präfix-Entfernung)."""
    body = SOAP_ENV.format(action=action, service=service,
                           args="".join(f"<{k}>{v}</{k}>" for k, v in (args or {}).items()))
    req = urllib.request.Request(control_url, data=body.encode("utf-8"), method="POST", headers={
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction": f'"{service}#{action}"',
        "User-Agent": "NetGuard",
    })
    op = opener or urllib.request.build_opener()
    with op.open(req, timeout=timeout) as resp:
        raw = resp.read(2_000_000).decode("utf-8", errors="replace")
    if "<s:Fault" in raw or "<SOAP-ENV:Fault" in raw:
        m = re.search(r"<errorDescription>(.*?)</errorDescription>", raw, re.S)
        raise RuntimeError("SOAP-Fehler: " + (m.group(1) if m else "unbekannt"))
    out: dict[str, str] = {}
    for m in re.finditer(r"<(New[A-Za-z0-9_\-]+)>(.*?)</\1>", raw, re.S):
        out[m.group(1)] = _unescape(m.group(2).strip())
    return out


def _unescape(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")


@dataclass
class ServiceInfo:
    service_type: str
    control_url: str


def parse_services(desc_url: str, raw: bytes) -> tuple[dict[str, str], dict[str, ServiceInfo]]:
    """Liest Gerätebeschreibung: (Geräteinfos, Dienste nach Typ-Kurzname z.B. 'WANCommonInterfaceConfig')."""
    info: dict[str, str] = {}
    services: dict[str, ServiceInfo] = {}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return info, services
    base = ""
    for el in root.iter():
        if _strip(el.tag) == "URLBase" and el.text:
            base = el.text.strip()
            break
    if not base:
        m = re.match(r"^(https?://[^/]+)", desc_url)
        base = m.group(1) if m else desc_url
    first_device = True
    for el in root.iter():
        tag = _strip(el.tag)
        if tag == "device" and first_device:
            first_device = False
            for ch in el:
                t = _strip(ch.tag)
                if t in ("friendlyName", "modelName", "manufacturer", "modelDescription", "presentationURL"):
                    info[t] = (ch.text or "").strip()
        if tag == "service":
            st = cu = ""
            for ch in el:
                t = _strip(ch.tag)
                if t == "serviceType":
                    st = (ch.text or "").strip()
                elif t == "controlURL":
                    cu = (ch.text or "").strip()
            if st and cu:
                short = st.split(":")[-2] if ":" in st else st
                url = cu if cu.lower().startswith("http") else urllib.parse.urljoin(base + "/", cu.lstrip("/"))
                services.setdefault(short, ServiceInfo(st, url))
    return info, services


# ---------------------------------------------------------------------------
# UPnP-IGD (ohne Login)
# ---------------------------------------------------------------------------
@dataclass
class WanStatus:
    ok: bool = False
    source: str = ""
    error: str = ""
    model: str = ""
    external_ip: str = ""
    uptime_s: int | None = None
    connection_status: str = ""
    link_down_bps: int | None = None     # max. Downstream (bit/s)
    link_up_bps: int | None = None
    total_rx: int | None = None          # Byte gesamt empfangen (WAN)
    total_tx: int | None = None
    rate_rx_bps: float | None = None     # aktuelle Rate (Byte/s), vom Router gemeldet
    rate_tx_bps: float | None = None
    history_rx: list[int] = field(default_factory=list)   # AVM Online-Monitor (Byte/s, alle 5 s)
    history_tx: list[int] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


def find_igd(router_ip: str, timeout: float = 2.5) -> str:
    """Sucht die IGD-Beschreibungs-URL des Routers (SSDP, dann bekannte Adressen)."""
    try:
        found = ssdpmod.discover(timeout)
    except Exception:
        found = {}
    for ip, info in found.items():
        loc = info.get("location", "")
        if ip == router_ip and loc and "InternetGatewayDevice" in (info.get("st", "") + info.get("usn", "")):
            return loc
    for ip, info in found.items():
        loc = info.get("location", "")
        if loc and "InternetGatewayDevice" in (info.get("st", "") + info.get("usn", "")):
            return loc
    for cand in (f"http://{router_ip}:49000/igddesc.xml", f"http://{router_ip}:49000/igd2desc.xml",
                 f"http://{router_ip}:5000/rootDesc.xml", f"http://{router_ip}:1900/igd.xml",
                 f"http://{router_ip}:49152/IGDdevicedesc.xml", f"http://{router_ip}:2869/upnphost/udhisapi.dll?content=uuid:igd"):
        try:
            raw = _get(cand, 2.0)
            if b"InternetGatewayDevice" in raw:
                return cand
        except Exception:
            continue
    return ""


def query_wan(router_ip: str, desc_url: str = "") -> WanStatus:
    st = WanStatus(source="UPnP-IGD")
    desc_url = desc_url or find_igd(router_ip)
    if not desc_url:
        st.error = "Kein UPnP-IGD gefunden. Am Router prüfen, ob UPnP/Statusinformationen freigegeben sind (Fritz!Box: Heimnetz → Netzwerk → Netzwerkeinstellungen → „Statusinformationen über UPnP übertragen“)."
        return st
    try:
        info, services = parse_services(desc_url, _get(desc_url))
    except Exception as exc:
        st.error = f"Beschreibung nicht lesbar: {exc}"
        return st
    st.model = " ".join(x for x in (info.get("manufacturer", ""), info.get("modelName", "")) if x) or info.get("friendlyName", "")
    wcic = services.get("WANCommonInterfaceConfig")
    wanip = services.get("WANIPConnection") or services.get("WANPPPConnection")
    if wcic is None and wanip is None:
        st.error = "Router bietet keine WAN-Dienste über UPnP an."
        return st
    if wcic is not None:
        try:
            r = soap_call(wcic.control_url, wcic.service_type, "GetCommonLinkProperties")
            st.link_down_bps = _int(r.get("NewLayer1DownstreamMaxBitRate"))
            st.link_up_bps = _int(r.get("NewLayer1UpstreamMaxBitRate"))
            st.connection_status = r.get("NewPhysicalLinkStatus", "")
        except Exception:
            pass
        try:
            r = soap_call(wcic.control_url, wcic.service_type, "GetAddonInfos")   # AVM
            st.rate_rx_bps = _float(r.get("NewByteReceiveRate"))
            st.rate_tx_bps = _float(r.get("NewByteSendRate"))
            st.total_rx = _int(r.get("NewX_AVM_DE_TotalBytesReceived64")) or _int(r.get("NewTotalBytesReceived"))
            st.total_tx = _int(r.get("NewX_AVM_DE_TotalBytesSent64")) or _int(r.get("NewTotalBytesSent"))
        except Exception:
            pass
        if st.total_rx is None:
            try:
                st.total_rx = _int(soap_call(wcic.control_url, wcic.service_type, "GetTotalBytesReceived").get("NewTotalBytesReceived"))
                st.total_tx = _int(soap_call(wcic.control_url, wcic.service_type, "GetTotalBytesSent").get("NewTotalBytesSent"))
            except Exception as exc:
                st.error = f"WAN-Zähler nicht abrufbar: {exc}"
        try:
            r = soap_call(wcic.control_url, wcic.service_type, "X_AVM-DE_GetOnlineMonitor", {"NewSyncGroupIndex": "0"})
            st.history_rx = [int(x) for x in r.get("Newds_current_bps", "").split(",") if x.strip().isdigit()]
            st.history_tx = [int(x) for x in r.get("Newus_current_bps", "").split(",") if x.strip().isdigit()]
            if st.link_down_bps is None:
                st.link_down_bps = _int(r.get("Newmax_ds"))
                st.link_up_bps = _int(r.get("Newmax_us"))
        except Exception:
            pass
    if wanip is not None:
        try:
            r = soap_call(wanip.control_url, wanip.service_type, "GetExternalIPAddress")
            st.external_ip = r.get("NewExternalIPAddress", "")
        except Exception:
            pass
        try:
            r = soap_call(wanip.control_url, wanip.service_type, "GetStatusInfo")
            st.uptime_s = _int(r.get("NewUptime"))
            st.connection_status = r.get("NewConnectionStatus", st.connection_status)
        except Exception:
            pass
    st.ok = st.total_rx is not None or st.external_ip != "" or st.uptime_s is not None
    if not st.ok and not st.error:
        st.error = "Router hat auf die UPnP-Abfragen nicht geantwortet."
    return st


def _int(v: str | None) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# TR-064 (Fritz!Box und kompatible), mit Login
# ---------------------------------------------------------------------------
@dataclass
class RouterHost:
    ip: str
    mac: str
    name: str
    active: bool
    interface: str = ""        # Ethernet / 802.11 / ...
    speed_mbps: int | None = None
    port: str = ""
    guest: bool = False
    rssi: int | None = None
    rx_rate_kbps: int | None = None   # aktuelle Link-Rate laut Mesh (kbit/s)
    tx_rate_kbps: int | None = None
    source: str = "TR-064"


@dataclass
class RouterHosts:
    ok: bool = False
    error: str = ""
    model: str = ""
    hosts: list[RouterHost] = field(default_factory=list)


def tr064_opener(router_ip: str, user: str, password: str):
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, f"http://{router_ip}:49000/", user, password)
    return urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))


def query_tr064_hosts(router_ip: str, user: str, password: str) -> RouterHosts:
    res = RouterHosts()
    base = f"http://{router_ip}:49000"
    try:
        raw = _get(base + "/tr64desc.xml", 4.0)
    except Exception as exc:
        res.error = f"TR-064 nicht erreichbar ({exc}). Fritz!Box: Heimnetz → Netzwerk → Netzwerkeinstellungen → „Zugriff für Anwendungen zulassen“ einschalten."
        return res
    info, services = parse_services(base + "/tr64desc.xml", raw)
    res.model = " ".join(x for x in (info.get("manufacturer", ""), info.get("modelName", "")) if x)
    hosts_svc = services.get("Hosts")
    if hosts_svc is None:
        res.error = "Router bietet keinen Hosts-Dienst über TR-064 an."
        return res
    opener = tr064_opener(router_ip, user or "admin", password)
    by_mac: dict[str, RouterHost] = {}
    # 1) Vollständige Geräteliste (AVM) – eine Abfrage
    try:
        r = soap_call(hosts_svc.control_url, hosts_svc.service_type, "X_AVM-DE_GetHostListPath", opener=opener)
        path = r.get("NewX_AVM-DE_HostListPath", "")
        if path:
            xml = _get(base + path if path.startswith("/") else path, 10.0)
            for item in ET.fromstring(xml).iter("Item"):
                f = {_strip(c.tag): (c.text or "").strip() for c in item}
                mac = f.get("MACAddress", "").lower()
                h = RouterHost(ip=f.get("IPAddress", ""), mac=mac, name=f.get("HostName", ""), active=f.get("Active", "0") == "1",
                               interface=f.get("InterfaceType", ""), speed_mbps=_int(f.get("X_AVM-DE_Speed")),
                               port=f.get("X_AVM-DE_Port", ""), guest=f.get("X_AVM-DE_Guest", "0") == "1")
                by_mac[mac or h.ip] = h
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            res.error = "Anmeldung am Router abgelehnt (Benutzername/Passwort prüfen). Fritz!Box: Benutzer unter System → FRITZ!Box-Benutzer, Recht „FRITZ!Box Einstellungen“."
            return res
    except Exception:
        pass
    # 2) Standardweg (alle TR-064-Router): Einträge einzeln
    if not by_mac:
        try:
            n = _int(soap_call(hosts_svc.control_url, hosts_svc.service_type, "GetHostNumberOfEntries", opener=opener).get("NewHostNumberOfEntries")) or 0
            for i in range(min(n, 512)):
                r = soap_call(hosts_svc.control_url, hosts_svc.service_type, "GetGenericHostEntry", {"NewIndex": str(i)}, opener=opener)
                mac = r.get("NewMACAddress", "").lower()
                h = RouterHost(ip=r.get("NewIPAddress", ""), mac=mac, name=r.get("NewHostName", ""), active=r.get("NewActive", "0") == "1",
                               interface=r.get("NewInterfaceType", ""))
                by_mac[mac or h.ip] = h
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                res.error = "Anmeldung am Router abgelehnt (Benutzername/Passwort prüfen)."
                return res
            res.error = f"Geräteliste nicht abrufbar: HTTP {exc.code}"
            return res
        except Exception as exc:
            res.error = f"Geräteliste nicht abrufbar: {exc}"
            return res
    # 3) Mesh-Liste (AVM): aktuelle Link-Raten und Signalstärke
    try:
        r = soap_call(hosts_svc.control_url, hosts_svc.service_type, "X_AVM-DE_GetMeshListPath", opener=opener)
        path = r.get("NewX_AVM-DE_MeshListPath", "")
        if path:
            mesh = json.loads(_get(base + path if path.startswith("/") else path, 10.0).decode("utf-8", errors="replace"))
            _apply_mesh(mesh, by_mac)
    except Exception:
        pass
    res.hosts = sorted(by_mac.values(), key=lambda h: h.ip)
    res.ok = True
    return res


def _apply_mesh(mesh: dict, by_mac: dict[str, RouterHost]) -> None:
    for node in mesh.get("nodes", []):
        macs = {str(i.get("mac_address", "")).lower() for i in node.get("node_interfaces", [])}
        macs.add(str(node.get("device_mac_address", "")).lower())
        target = next((by_mac[m] for m in macs if m in by_mac), None)
        if target is None:
            continue
        best_rx = best_tx = None
        rssi = None
        for iface in node.get("node_interfaces", []):
            for link in iface.get("node_links", []):
                if link.get("state") not in (None, "CONNECTED"):
                    continue
                rx = link.get("cur_data_rate_rx")
                tx = link.get("cur_data_rate_tx")
                if isinstance(rx, int) and (best_rx is None or rx > best_rx):
                    best_rx = rx
                if isinstance(tx, int) and (best_tx is None or tx > best_tx):
                    best_tx = tx
                r = link.get("rx_rssi")
                if isinstance(r, int) and r != 0 and r != -1:
                    rssi = r if rssi is None else max(rssi, r)
        target.rx_rate_kbps = best_rx
        target.tx_rate_kbps = best_tx
        target.rssi = rssi


def human_bytes(n: float | int | None) -> str:
    if n is None:
        return "–"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_rate(bps: float | None) -> str:
    """Byte/s als lesbare Rate."""
    if bps is None:
        return "–"
    bits = bps * 8
    for unit in ("bit/s", "kbit/s", "Mbit/s", "Gbit/s"):
        if bits < 1000 or unit == "Gbit/s":
            return f"{bits:.0f} {unit}" if unit == "bit/s" else f"{bits:.1f} {unit}"
        bits /= 1000
    return f"{bits:.1f} Gbit/s"


def human_uptime(s: int | None) -> str:
    if s is None:
        return "–"
    d, rem = divmod(int(s), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return (f"{d} T " if d else "") + f"{h:02d}:{m:02d} h"
