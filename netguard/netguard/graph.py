"""Topologie-Graph aus einem Scan (ohne GUI-Abhängigkeiten)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import Scan, Device, DeviceDiff, STATUS_NEW, STATUS_MISSING, STATUS_CHANGED
from .classify import type_label

STATUS_COLORS = {STATUS_NEW: "#2ee6a6", STATUS_MISSING: "#ff5c5c", STATUS_CHANGED: "#ffb347"}


@dataclass
class NodeData:
    id: str
    kind: str                     # "internet" | "device" | "subnet"
    title: str
    subtitle: str = ""
    dtype: str = "unknown"
    device: Device | None = None
    status: str = ""              # neu / fehlt / geändert / ""
    changes: list[str] = field(default_factory=list)


def node_title(d: Device) -> str:
    """Beschriftung eines Geräteknotens: Name, sonst Hersteller, sonst Typ."""
    if d.display_name != d.ip:
        return d.display_name
    if d.is_self:
        return "Dieser Computer"
    if d.is_gateway:
        return "Router" + (f" ({d.vendor})" if d.vendor and not d.vendor.startswith("(") else "")
    if d.vendor and not d.vendor.startswith("("):
        return d.vendor
    return type_label(d.device_type)


# ---------------------------------------------------------------------------
# Baum aufbauen
# ---------------------------------------------------------------------------
def build_graph(scan: Scan, diffs: list[DeviceDiff] | None = None) -> tuple[dict[str, NodeData], list[tuple[str, str]], str]:
    """Liefert (Knoten, Kanten (Eltern, Kind), Wurzel für das Layout)."""
    nodes: dict[str, NodeData] = {}
    parent: dict[str, str] = {}
    status_by_key: dict[str, DeviceDiff] = {}
    missing: list[Device] = []
    if diffs:
        for df in diffs:
            if df.status == STATUS_MISSING and df.previous is not None:
                missing.append(df.previous)
            elif df.current is not None:
                status_by_key[df.current.key] = df

    nodes["internet"] = NodeData("internet", "internet", "Internet", scan.public_ip or ("erreichbar" if scan.internet_ok else "nicht erreichbar" if scan.internet_ok is False else ""), "internet")

    devices = list(scan.devices)
    by_ip = {d.ip: d for d in devices}

    def add_device(d: Device, status: str = "", changes: list[str] | None = None) -> str:
        nid = "dev:" + d.ip
        if nid in nodes:
            return nid
        nodes[nid] = NodeData(nid, "device", node_title(d), d.ip, d.device_type, d, status, changes or [])
        return nid

    for d in devices:
        df = status_by_key.get(d.key)
        add_device(d, df.status if df and df.status in STATUS_COLORS else "", df.changes if df else [])

    def set_parent(child: str, par: str) -> None:
        if child == par or child in parent:
            return
        # Zyklen vermeiden
        x = par
        guard = 0
        while x in parent and guard < 1000:
            if x == child:
                return
            x = parent[x]
            guard += 1
        parent[child] = par

    gateways = [g for g in scan.gateways if g in by_ip]
    main_gw = gateways[0] if gateways else ""
    self_dev = next((d for d in devices if d.is_self), None)
    self_id = "dev:" + self_dev.ip if self_dev else ""

    # Weg ins Internet: gw -> private Hops -> Internet
    chain = [h for h in scan.internet_path if h in by_ip]
    if main_gw and main_gw not in chain:
        chain.insert(0, main_gw)
    for i, hop in enumerate(chain):
        nxt = "dev:" + chain[i + 1] if i + 1 < len(chain) else "internet"
        set_parent("dev:" + hop, nxt)
    if not chain:
        if self_id:
            set_parent(self_id, "internet")

    # Eigener Rechner hängt am Haupt-Gateway, weitere Gateways hängen am eigenen Rechner
    if self_id and main_gw:
        set_parent(self_id, "dev:" + main_gw)
    for g in gateways[1:]:
        set_parent("dev:" + g, self_id or ("dev:" + main_gw if main_gw else "internet"))

    # Gateway je Subnetz bestimmen
    gw_by_subnet: dict[str, str] = {}
    for i in scan.interfaces:
        if i.cidr and i.gateway in by_ip:
            gw_by_subnet[i.cidr] = i.gateway
    for d in devices:
        if d.is_gateway and d.subnet and d.subnet not in gw_by_subnet:
            gw_by_subnet[d.subnet] = d.ip

    for d in devices:
        nid = "dev:" + d.ip
        if nid in parent:
            continue
        # Traceroute-Pfad: letzter Hop ist der nächste Router
        hops = [h for h in d.hops if h in by_ip and h != d.ip]
        if hops:
            set_parent(nid, "dev:" + hops[-1])
            for j in range(len(hops) - 1, 0, -1):
                set_parent("dev:" + hops[j], "dev:" + hops[j - 1])
            first = "dev:" + hops[0]
            if first not in parent:
                set_parent(first, "dev:" + main_gw if main_gw and hops[0] != main_gw else (self_id or "internet"))
            continue
        gw = gw_by_subnet.get(d.subnet, "")
        if gw and gw != d.ip:
            set_parent(nid, "dev:" + gw)
            continue
        # kein Gateway bekannt: Subnetz-Knoten
        sid = "subnet:" + (d.subnet or "?")
        if sid not in nodes:
            nodes[sid] = NodeData(sid, "subnet", d.subnet or "Subnetz", "ohne bekanntes Gateway", "switch")
            set_parent(sid, self_id or ("dev:" + main_gw if main_gw else "internet"))
        set_parent(nid, sid)

    # Verschwundene Geräte aus dem Vergleichs-Scan (gestrichelt)
    for d in missing:
        nid = "dev:" + d.ip
        if nid in nodes:
            nid = "missing:" + d.key
        nodes[nid] = NodeData(nid, "device", node_title(d), d.ip, d.device_type, d, STATUS_MISSING)
        gw = gw_by_subnet.get(d.subnet, "")
        set_parent(nid, "dev:" + gw if gw and gw != d.ip else (self_id or "internet"))

    # Alles ohne Eltern hängt am Internet (außer Internet selbst)
    for nid in nodes:
        if nid != "internet" and nid not in parent:
            set_parent(nid, "dev:" + main_gw if main_gw and nid != "dev:" + main_gw else "internet")

    edges = [(p, c) for c, p in parent.items()]
    root = "dev:" + main_gw if main_gw else (self_id or "internet")
    return nodes, edges, root


