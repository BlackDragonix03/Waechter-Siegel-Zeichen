"""Die MCP-Tools: Beschreibung, Eingabeschema und Ausführung."""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Callable

from .. import storage, diagnostics
from ..model import Scan, Device, compare_scans
from ..classify import type_label, TYPES
from ..graph import build_graph
from ..net import local, ping as pingmod, trace as tracemod, ports as portsmod, names as namesmod, router as routermod, snmp as snmpmod
from ..net.engine import ScanOptions, internet_check
from .backend import Backend


@dataclass
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    fn: Callable[[Backend, dict[str, Any]], Any]


def _dev(d: Device, full: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ip": d.ip, "mac": d.mac, "name": d.display_name if d.display_name != d.ip else "",
        "vendor": d.vendor, "type": d.device_type, "type_label": type_label(d.device_type),
        "open_ports": d.open_ports, "latency_ms": d.latency_ms, "subnet": d.subnet,
        "is_gateway": d.is_gateway, "is_self": d.is_self, "admin_url": d.admin_url, "trusted": d.trusted,
    }
    if d.online is not None:
        out["online"] = d.online
    if d.router_active is not None:
        out["router"] = {"active": d.router_active, "interface": d.router_iface, "speed_mbps": d.router_speed_mbps, "rssi": d.router_rssi}
    if full:
        out.update({
            "hostname_dns": d.hostname, "name_netbios": d.netbios_name, "name_mdns": d.mdns_name, "name_upnp": d.ssdp_name,
            "model_upnp": d.ssdp_model, "upnp_type": d.ssdp_type, "services": d.services, "alive_via": d.alive_via,
            "interface": d.interface, "hops": d.hops, "custom_name": d.custom_name, "note": d.note,
            "first_seen": d.first_seen, "last_seen": d.last_seen,
        })
    return out


def _scan_summary(scan: Scan) -> dict[str, Any]:
    return {
        "id": scan.id, "name": scan.name, "started": scan.started, "finished": scan.finished, "duration_s": scan.duration_s,
        "targets": scan.targets, "discovered_subnets": scan.discovered, "device_count": len(scan.devices),
        "gateways": scan.gateways, "internet_ok": scan.internet_ok, "dns_ok": scan.dns_ok, "public_ip": scan.public_ip,
        "internet_path": scan.internet_path,
        "interfaces": [i.to_dict() for i in scan.interfaces],
        "problem_count": len(scan.problems),
    }


def _find_device(scan: Scan | None, key: str) -> Device | None:
    if scan is None:
        return None
    key = (key or "").strip().lower()
    for d in scan.devices:
        if d.ip == key or (d.mac and d.mac.lower() == key.replace("-", ":")):
            return d
    for d in scan.devices:
        if key and key in d.display_name.lower():
            return d
    return None


def _need_scan(b: Backend) -> Scan:
    scan = b.current_scan()
    if scan is None:
        raise ValueError("Noch kein Scan vorhanden. Zuerst scan_network aufrufen.")
    return scan


# ---------------------------------------------------------------------------
def t_scan_network(b: Backend, a: dict[str, Any]) -> Any:
    targets = [t.strip() for t in str(a.get("targets", "") or "").replace(";", ",").split(",") if t.strip()]
    opts = ScanOptions(
        targets=targets,
        discover=str(a.get("discover", "none") or "none"),
        port_mode=str(a.get("ports", "quick") or "quick"),
        resolve_names=bool(a.get("names", True)),
        netbios=bool(a.get("names", True)),
        mdns=bool(a.get("names", True)),
        upnp=bool(a.get("upnp", True)),
        traceroute=bool(a.get("traceroute", True)),
    )
    if opts.discover not in ("none", "quick", "full"):
        raise ValueError("discover muss none, quick oder full sein")
    if opts.port_mode not in ("none", "quick", "full"):
        raise ValueError("ports muss none, quick oder full sein")
    scan = b.run_scan(opts)
    return {"scan": _scan_summary(scan), "devices": [_dev(d) for d in scan.sorted_devices()], "problems": scan.problems}


def t_get_current_scan(b: Backend, a: dict[str, Any]) -> Any:
    scan = _need_scan(b)
    return {"scan": _scan_summary(scan), "devices": [_dev(d) for d in scan.sorted_devices()], "problems": scan.problems}


def t_get_devices(b: Backend, a: dict[str, Any]) -> Any:
    scan = _need_scan(b)
    text = str(a.get("filter", "") or "").lower()
    typ = str(a.get("type", "") or "")
    out = []
    for d in scan.sorted_devices():
        if typ and d.device_type != typ:
            continue
        if text:
            hay = " ".join((d.ip, d.mac, d.vendor, d.hostname, d.netbios_name, d.mdns_name, d.ssdp_name, d.custom_name, d.note, d.subnet)).lower()
            if text not in hay:
                continue
        out.append(_dev(d))
    return {"count": len(out), "devices": out}


def t_get_device(b: Backend, a: dict[str, Any]) -> Any:
    d = _find_device(_need_scan(b), str(a.get("device", "")))
    if d is None:
        raise ValueError("Gerät nicht gefunden (IP, MAC oder Name angeben).")
    return _dev(d, full=True)


def t_get_problems(b: Backend, a: dict[str, Any]) -> Any:
    scan = _need_scan(b)
    return {"problems": scan.problems or diagnostics.analyze(scan)}


def t_get_topology(b: Backend, a: dict[str, Any]) -> Any:
    scan = _need_scan(b)
    nodes, edges, root = build_graph(scan)
    return {
        "root": root,
        "nodes": [{"id": n.id, "kind": n.kind, "title": n.title, "subtitle": n.subtitle, "type": n.dtype,
                   "ip": n.device.ip if n.device else None} for n in nodes.values()],
        "edges": [{"parent": p, "child": c} for p, c in edges],
    }


def t_list_scans(b: Backend, a: dict[str, Any]) -> Any:
    return {"scans": [dict(info, path=str(p)) for p, info in storage.list_scans()[: int(a.get("limit", 50) or 50)]]}


def _load_by_id(scan_id: str) -> Scan:
    for p, info in storage.list_scans():
        if info["id"] == scan_id or p.name == scan_id:
            return storage.load_scan(p)
    raise ValueError(f"Scan {scan_id} nicht gefunden (list_scans zeigt die IDs).")


def t_load_scan(b: Backend, a: dict[str, Any]) -> Any:
    scan = _load_by_id(str(a.get("scan_id", "")))
    b.set_current_scan(scan)
    return {"scan": _scan_summary(scan), "devices": [_dev(d) for d in scan.sorted_devices()]}


def t_compare_scans(b: Backend, a: dict[str, Any]) -> Any:
    cur = _load_by_id(str(a["current_id"])) if a.get("current_id") else _need_scan(b)
    if a.get("previous_id"):
        prev = _load_by_id(str(a["previous_id"]))
    else:
        items = [x for x in storage.list_scans() if x[1]["id"] != cur.id]
        if not items:
            raise ValueError("Kein älterer Scan zum Vergleich vorhanden.")
        prev = storage.load_scan(items[0][0])
    diffs = compare_scans(cur, prev)
    out = {"current": _scan_summary(cur), "previous": _scan_summary(prev), "new": [], "changed": [], "missing": [], "unchanged": 0}
    for df in diffs:
        if df.status == "neu":
            out["new"].append(_dev(df.device))
        elif df.status == "geändert":
            out["changed"].append(dict(_dev(df.device), changes=df.changes))
        elif df.status == "fehlt":
            out["missing"].append(_dev(df.device))
        else:
            out["unchanged"] += 1
    return out


def t_set_device_info(b: Backend, a: dict[str, Any]) -> Any:
    scan = _need_scan(b)
    d = _find_device(scan, str(a.get("device", "")))
    if d is None:
        raise ValueError("Gerät nicht gefunden.")
    if "name" in a and a["name"] is not None:
        d.custom_name = str(a["name"]).strip()
    if "note" in a and a["note"] is not None:
        d.note = str(a["note"]).strip()
    if "trusted" in a and a["trusted"] is not None:
        d.trusted = bool(a["trusted"])
    if a.get("type"):
        if a["type"] not in TYPES:
            raise ValueError("Unbekannter Typ. Erlaubt: " + ", ".join(k for k in TYPES if k != "internet"))
        d.device_type = str(a["type"])
    b.save_device(d)
    return _dev(d, full=True)


def _resolve(host: str) -> str:
    host = (host or "").strip()
    if not host:
        raise ValueError("host fehlt")
    try:
        return socket.gethostbyname(host)
    except OSError:
        raise ValueError(f"Name {host} konnte nicht aufgelöst werden.")


def t_ping(b: Backend, a: dict[str, Any]) -> Any:
    ip = _resolve(str(a.get("host", "")))
    count = max(1, min(int(a.get("count", 4) or 4), 20))
    results = []
    for _ in range(count):
        ok, rtt = pingmod.ping(ip, 1000, allow_tcp=False)
        results.append({"reply": ok, "ms": rtt})
    ok_n = sum(1 for r in results if r["reply"])
    rtts = [r["ms"] for r in results if r["reply"] and r["ms"] is not None]
    return {"host": a.get("host"), "ip": ip, "sent": count, "received": ok_n, "loss_percent": round(100 * (count - ok_n) / count),
            "min_ms": min(rtts) if rtts else None, "avg_ms": round(sum(rtts) / len(rtts), 1) if rtts else None, "max_ms": max(rtts) if rtts else None}


def t_traceroute(b: Backend, a: dict[str, Any]) -> Any:
    ip = _resolve(str(a.get("host", "")))
    hops = []
    for hop, addr, rtt in tracemod.traceroute(ip, int(a.get("max_hops", 30) or 30), 1500):
        hops.append({"hop": hop, "ip": addr or None, "ms": rtt, "name": namesmod.reverse_dns(addr, 0.8) if addr else None})
    return {"ip": ip, "hops": hops}


def t_port_check(b: Backend, a: dict[str, Any]) -> Any:
    ip = _resolve(str(a.get("host", "")))
    plist = a.get("ports")
    if isinstance(plist, str):
        plist = [int(x) for x in plist.replace(";", ",").split(",") if x.strip().isdigit()]
    if not plist:
        plist = portsmod.FULL_PORTS
    found = portsmod.scan_ports(ip, [int(p) for p in plist][:1024], timeout=0.8, workers=48)
    out = []
    for p in found:
        entry: dict[str, Any] = {"port": p, "service": portsmod.service_name(p)}
        if p in (80, 443, 8080, 8443, 5000, 5001, 8000, 8123):
            t, s = portsmod.http_title(ip, p)
            entry["http_title"] = t
            entry["server"] = s
        elif p == 22:
            entry["banner"] = portsmod.banner(ip, p)
        out.append(entry)
    return {"ip": ip, "checked": len(plist), "open": out}


def t_resolve_name(b: Backend, a: dict[str, Any]) -> Any:
    host = str(a.get("host", "")).strip()
    out: dict[str, Any] = {"host": host}
    try:
        out["addresses"] = sorted({i[4][0] for i in socket.getaddrinfo(host, None)})
    except OSError as exc:
        out["addresses"] = []
        out["error"] = str(exc)
    for ip in [x for x in out["addresses"] if ":" not in x][:2]:
        nb, grp = namesmod.netbios_name(ip, 1.0)
        out[ip] = {"reverse_dns": namesmod.reverse_dns(ip), "netbios": nb, "workgroup": grp, "mdns": namesmod.mdns_name(ip, 1.0)}
    return out


def t_network_info(b: Backend, a: dict[str, Any]) -> Any:
    ifaces = local.interfaces()
    dns_ok, net_ok, public_ip = internet_check()
    return {"interfaces": [i.to_dict() for i in ifaces], "gateways": local.gateways(ifaces), "default_targets": local.default_targets(ifaces),
            "dns_ok": dns_ok, "internet_ok": net_ok, "public_ip": public_ip}


def _router_ip(b: Backend, a: dict[str, Any]) -> str:
    ip = str(a.get("router_ip", "") or "").strip() or str(b.settings().get("router_ip", "") or "")
    if not ip:
        scan = b.current_scan()
        if scan and scan.gateways:
            ip = scan.gateways[0]
    if not ip:
        gws = local.gateways(local.interfaces())
        ip = gws[0] if gws else ""
    if not ip:
        raise ValueError("Router-IP unbekannt. router_ip angeben.")
    return ip


def t_router_wan_status(b: Backend, a: dict[str, Any]) -> Any:
    ip = _router_ip(b, a)
    st = routermod.query_wan(ip)
    out = {k: v for k, v in st.__dict__.items() if k not in ("history_rx", "history_tx", "timestamp")}
    out["router_ip"] = ip
    out["total_rx_human"] = routermod.human_bytes(st.total_rx)
    out["total_tx_human"] = routermod.human_bytes(st.total_tx)
    out["rate_rx_human"] = routermod.human_rate(st.rate_rx_bps)
    out["rate_tx_human"] = routermod.human_rate(st.rate_tx_bps)
    out["uptime_human"] = routermod.human_uptime(st.uptime_s)
    if st.history_rx:
        out["online_monitor_last_values_bytes_per_s"] = {"download": st.history_rx, "upload": st.history_tx}
    return out


def t_router_hosts(b: Backend, a: dict[str, Any]) -> Any:
    ip = _router_ip(b, a)
    s = b.settings()
    user = str(a.get("user") or s.get("tr064_user") or "")
    pw = str(a.get("password") or s.get("tr064_password") or "")
    if not pw:
        raise ValueError("Router-Passwort fehlt (password angeben oder im Reiter „Live & Router“ speichern).")
    res = routermod.query_tr064_hosts(ip, user, pw)
    if not res.ok:
        raise ValueError(res.error)
    return {"router_ip": ip, "model": res.model, "count": len(res.hosts), "active": sum(1 for h in res.hosts if h.active),
            "hosts": [h.__dict__ for h in res.hosts]}


def t_snmp_interfaces(b: Backend, a: dict[str, Any]) -> Any:
    ip = _resolve(str(a.get("host", "")))
    comm = str(a.get("community") or b.settings().get("snmp_community") or "public")
    res = snmpmod.query_interfaces(ip, comm, 2.0)
    if not res.ok:
        raise ValueError(res.error)
    return {"ip": ip, "sys_name": res.sys_name, "sys_descr": res.sys_descr, "uptime_s": res.uptime_s,
            "interfaces": [i.__dict__ for i in res.interfaces]}


# ---------------------------------------------------------------------------
def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    s: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        s["required"] = required
    return s


TOOLS: list[Tool] = [
    Tool("scan_network",
         "Scannt das Netzwerk und liefert alle gefundenen Geräte (IP, MAC, Hersteller, Namen, Typ, Ports, Zugangs-URL) "
         "sowie erkannte Probleme. Ohne targets werden die eigenen Subnetze gescannt. discover=quick/full sucht zusätzlich "
         "versteckte Subnetze in allen privaten Bereichen (dauert 1 bis 10 Minuten). Der Scan wird gespeichert.",
         _obj({"targets": {"type": "string", "description": "Komma-getrennt: CIDR, Bereich oder IP, z.B. '192.168.178.0/24, 10.0.0.1-50'. Leer = eigene Subnetze."},
               "discover": {"type": "string", "enum": ["none", "quick", "full"], "description": "Versteckte Subnetze suchen (Standard none)."},
               "ports": {"type": "string", "enum": ["none", "quick", "full"], "description": "Portprüfung (Standard quick)."},
               "names": {"type": "boolean", "description": "Namen per DNS/NetBIOS/mDNS auflösen (Standard true)."},
               "upnp": {"type": "boolean"}, "traceroute": {"type": "boolean"}}), t_scan_network),
    Tool("get_current_scan", "Liefert den aktuellen (zuletzt durchgeführten oder geladenen) Scan mit Geräten und Problemen, ohne neu zu scannen.", _obj({}), t_get_current_scan),
    Tool("get_devices", "Geräte des aktuellen Scans, optional gefiltert nach Text (IP, MAC, Name, Hersteller) und Typ.",
         _obj({"filter": {"type": "string"}, "type": {"type": "string", "enum": [k for k in TYPES if k != "internet"]}}), t_get_devices),
    Tool("get_device", "Alle Details zu einem Gerät (IP, MAC oder Name).", _obj({"device": {"type": "string"}}, ["device"]), t_get_device),
    Tool("get_problems", "Erkannte Netzwerkprobleme des aktuellen Scans mit Lösungsvorschlägen.", _obj({}), t_get_problems),
    Tool("get_topology", "Netzwerk-Topologie des aktuellen Scans als Knoten und Kanten (Internet, Router, Subnetze, Geräte).", _obj({}), t_get_topology),
    Tool("list_scans", "Gespeicherte Scans (neueste zuerst) mit ID, Zeitpunkt, Zielen und Geräteanzahl.", _obj({"limit": {"type": "integer"}}), t_list_scans),
    Tool("load_scan", "Lädt einen gespeicherten Scan als aktuellen Scan.", _obj({"scan_id": {"type": "string"}}, ["scan_id"]), t_load_scan),
    Tool("compare_scans", "Vergleicht zwei Scans: neue, geänderte und fehlende Geräte. Ohne Angaben: aktueller Scan gegen den davor.",
         _obj({"current_id": {"type": "string"}, "previous_id": {"type": "string"}}), t_compare_scans),
    Tool("set_device_info", "Setzt eigenen Namen, Notiz, Typ oder die Markierung 'bekannt/vertrauenswürdig' für ein Gerät (bleibt dauerhaft gespeichert).",
         _obj({"device": {"type": "string"}, "name": {"type": "string"}, "note": {"type": "string"}, "trusted": {"type": "boolean"},
               "type": {"type": "string", "enum": [k for k in TYPES if k != "internet"]}}, ["device"]), t_set_device_info),
    Tool("ping", "Pingt einen Host mehrfach und liefert Verlust und Laufzeiten.", _obj({"host": {"type": "string"}, "count": {"type": "integer"}}, ["host"]), t_ping),
    Tool("traceroute", "Zeigt den Pfad (Router-Hops) zu einem Host.", _obj({"host": {"type": "string"}, "max_hops": {"type": "integer"}}, ["host"]), t_traceroute),
    Tool("port_check", "Prüft TCP-Ports eines Hosts (Standard: alle bekannten Dienste) und liest HTTP-Titel/SSH-Banner.",
         _obj({"host": {"type": "string"}, "ports": {"type": "string", "description": "Komma-getrennte Ports, leer = alle bekannten"}}, ["host"]), t_port_check),
    Tool("resolve_name", "Löst einen Namen oder eine IP auf: DNS, Reverse-DNS, NetBIOS, mDNS.", _obj({"host": {"type": "string"}}, ["host"]), t_resolve_name),
    Tool("network_info", "Eigene Schnittstellen, Gateways, DNS-Server und ob Internet/DNS funktionieren.", _obj({}), t_network_info),
    Tool("router_wan_status", "Fragt den Router per UPnP ab: Gesamtverkehr, aktuelle Rate, Anschlussgeschwindigkeit, Uptime, externe IP.",
         _obj({"router_ip": {"type": "string"}}), t_router_wan_status),
    Tool("router_hosts", "Geräteliste des Routers per TR-064 (Fritz!Box): aktiv, LAN/WLAN, Geschwindigkeit, Signal. Braucht Router-Login.",
         _obj({"router_ip": {"type": "string"}, "user": {"type": "string"}, "password": {"type": "string"}}), t_router_hosts),
    Tool("snmp_interfaces", "Schnittstellen-Zähler eines Geräts per SNMP v2c (Switch, NAS, Router).",
         _obj({"host": {"type": "string"}, "community": {"type": "string"}}, ["host"]), t_snmp_interfaces),
]

TOOL_MAP = {t.name: t for t in TOOLS}


def tool_descriptions() -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "inputSchema": t.schema} for t in TOOLS]


def call_tool(backend: Backend, name: str, args: dict[str, Any] | None) -> tuple[str, bool]:
    """Führt ein Tool aus. Rückgabe (Text, Fehler?)."""
    t = TOOL_MAP.get(name)
    if t is None:
        return f"Unbekanntes Tool: {name}", True
    try:
        result = t.fn(backend, args or {})
        return json.dumps(result, ensure_ascii=False, default=str), False
    except ValueError as exc:
        return str(exc), True
    except Exception as exc:
        return f"Fehler in {name}: {exc!r}", True
