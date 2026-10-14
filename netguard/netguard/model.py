"""Datenmodell: Geräte, Scans, Vergleich zweier Scans."""
from __future__ import annotations

import datetime as _dt
import ipaddress
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


@dataclass
class Device:
    ip: str
    mac: str = ""
    hostname: str = ""          # Reverse-DNS
    netbios_name: str = ""      # Windows-Name (NetBIOS)
    mdns_name: str = ""         # Bonjour/Avahi
    ssdp_name: str = ""         # UPnP friendlyName
    ssdp_model: str = ""        # UPnP modelName / Hersteller
    ssdp_type: str = ""         # UPnP deviceType (z.B. InternetGatewayDevice)
    ssdp_location: str = ""     # UPnP Beschreibungs-URL
    vendor: str = ""            # Hersteller aus MAC (OUI)
    device_type: str = "unknown"
    open_ports: list[int] = field(default_factory=list)
    services: dict[str, str] = field(default_factory=dict)   # "80": "HTTP: Titel"
    latency_ms: float | None = None
    alive_via: list[str] = field(default_factory=list)       # icmp / arp / tcp / ssdp
    is_gateway: bool = False
    is_self: bool = False
    subnet: str = ""
    interface: str = ""
    hops: list[str] = field(default_factory=list)            # Traceroute-Pfad (ohne Ziel)
    admin_url: str = ""
    custom_name: str = ""       # vom Benutzer vergeben
    note: str = ""
    trusted: bool = False
    first_seen: str = ""
    last_seen: str = ""
    # Live / Router-Angaben (nicht aus dem eigenen Scan)
    online: bool | None = None          # letzte Live-Prüfung
    router_active: bool | None = None   # laut Router (TR-064) verbunden
    router_iface: str = ""              # Ethernet / 802.11 / ...
    router_speed_mbps: int | None = None
    router_rssi: int | None = None
    router_name: str = ""               # Name laut Router

    # ---- abgeleitete Werte -------------------------------------------------
    @property
    def key(self) -> str:
        """Schlüssel zum Wiedererkennen: MAC, sonst IP."""
        return self.mac.lower() if self.mac else "ip:" + self.ip

    @property
    def display_name(self) -> str:
        for cand in (self.custom_name, self.ssdp_name, self.netbios_name,
                     self.mdns_name, self.hostname, self.router_name):
            if cand:
                return cand
        return self.ip

    @property
    def any_name(self) -> str:
        """Erster bekannter Netzwerkname (ohne Benutzername)."""
        for cand in (self.netbios_name, self.mdns_name, self.hostname, self.ssdp_name, self.router_name):
            if cand:
                return cand
        return ""

    def ip_int(self) -> int:
        try:
            return int(ipaddress.ip_address(self.ip))
        except ValueError:
            return 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Device":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in d.items() if k in known}
        dev = cls(**clean)
        dev.services = {str(k): str(v) for k, v in (dev.services or {}).items()}
        return dev


@dataclass
class InterfaceInfo:
    name: str
    ip: str
    netmask: str
    gateway: str = ""
    mac: str = ""
    cidr: str = ""
    dns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InterfaceInfo":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Scan:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    started: str = field(default_factory=now_iso)
    finished: str = ""
    targets: list[str] = field(default_factory=list)
    discovered: list[str] = field(default_factory=list)      # per Subnetz-Suche gefundene Netze
    devices: list[Device] = field(default_factory=list)
    interfaces: list[InterfaceInfo] = field(default_factory=list)
    gateways: list[str] = field(default_factory=list)
    internet_path: list[str] = field(default_factory=list)   # Hops bis ins Internet
    internet_ok: bool | None = None
    dns_ok: bool | None = None
    public_ip: str = ""
    duration_s: float = 0.0
    options: dict[str, Any] = field(default_factory=dict)
    problems: list[dict[str, str]] = field(default_factory=list)

    # ----------------------------------------------------------------------
    def device_by_ip(self, ip: str) -> Device | None:
        for d in self.devices:
            if d.ip == ip:
                return d
        return None

    def device_by_key(self, key: str) -> Device | None:
        for d in self.devices:
            if d.key == key:
                return d
        return None

    def sorted_devices(self) -> list[Device]:
        return sorted(self.devices, key=lambda d: (d.subnet, d.ip_int()))

    def subnets(self) -> list[str]:
        seen: list[str] = []
        for d in self.devices:
            if d.subnet and d.subnet not in seen:
                seen.append(d.subnet)
        return seen

    @property
    def title(self) -> str:
        if self.name:
            return self.name
        return self.started.replace("T", " ")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["devices"] = [x.to_dict() for x in self.devices]
        d["interfaces"] = [x.to_dict() for x in self.interfaces]
        d["format"] = 1
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Scan":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in d.items() if k in known}
        clean["devices"] = [Device.from_dict(x) for x in d.get("devices", [])]
        clean["interfaces"] = [InterfaceInfo.from_dict(x) for x in d.get("interfaces", [])]
        return cls(**clean)


# ---------------------------------------------------------------------------
# Vergleich zweier Scans ("alte Werte überlagern")
# ---------------------------------------------------------------------------
STATUS_NEW = "neu"
STATUS_MISSING = "fehlt"
STATUS_CHANGED = "geändert"
STATUS_SAME = "unverändert"


@dataclass
class DeviceDiff:
    status: str
    current: Device | None
    previous: Device | None
    changes: list[str] = field(default_factory=list)

    @property
    def device(self) -> Device:
        return self.current or self.previous  # type: ignore[return-value]


def compare_scans(current: Scan, previous: Scan) -> list[DeviceDiff]:
    """Vergleicht den aktuellen Scan mit einem älteren.

    Geräte werden über die MAC-Adresse wiedererkannt, ohne MAC über die IP.
    """
    result: list[DeviceDiff] = []
    prev_by_key = {d.key: d for d in previous.devices}
    prev_by_ip = {d.ip: d for d in previous.devices}
    matched_prev: set[str] = set()

    for cur in current.devices:
        prev = prev_by_key.get(cur.key)
        if prev is None and not cur.mac:
            prev = prev_by_ip.get(cur.ip)
        if prev is None and cur.mac:
            # gleiche IP, aber damals ohne MAC bekannt
            cand = prev_by_ip.get(cur.ip)
            if cand is not None and not cand.mac:
                prev = cand
        if prev is None:
            result.append(DeviceDiff(STATUS_NEW, cur, None))
            continue
        matched_prev.add(prev.key)
        changes = _device_changes(cur, prev)
        result.append(DeviceDiff(STATUS_CHANGED if changes else STATUS_SAME, cur, prev, changes))

    for prev in previous.devices:
        if prev.key not in matched_prev:
            result.append(DeviceDiff(STATUS_MISSING, None, prev))
    return result


def _device_changes(cur: Device, prev: Device) -> list[str]:
    changes: list[str] = []
    if cur.ip != prev.ip:
        changes.append(f"IP {prev.ip} → {cur.ip}")
    if cur.mac and prev.mac and cur.mac.lower() != prev.mac.lower():
        changes.append(f"MAC {prev.mac} → {cur.mac}")
    if cur.any_name != prev.any_name and (cur.any_name or prev.any_name):
        changes.append(f"Name {prev.any_name or '–'} → {cur.any_name or '–'}")
    added = sorted(set(cur.open_ports) - set(prev.open_ports))
    removed = sorted(set(prev.open_ports) - set(cur.open_ports))
    if added:
        changes.append("Neue Ports: " + ", ".join(map(str, added)))
    if removed:
        changes.append("Geschlossene Ports: " + ", ".join(map(str, removed)))
    if cur.device_type != prev.device_type and prev.device_type != "unknown":
        changes.append(f"Typ {prev.device_type} → {cur.device_type}")
    if cur.is_gateway != prev.is_gateway:
        changes.append("Gateway-Rolle geändert")
    return changes


def merge_previous_values(current: Scan, previous: Scan) -> int:
    """Übernimmt Werte aus einem alten Scan, die im neuen fehlen.

    Zum Beispiel Namen, die ein Gerät diesmal nicht preisgegeben hat, oder die
    Benutzer-Bezeichnung. Gibt die Zahl der ergänzten Geräte zurück.
    """
    prev_by_key = {d.key: d for d in previous.devices}
    count = 0
    for cur in current.devices:
        prev = prev_by_key.get(cur.key)
        if prev is None:
            continue
        touched = False
        for attr in ("hostname", "netbios_name", "mdns_name", "ssdp_name", "ssdp_model",
                     "ssdp_type", "vendor", "custom_name", "note", "admin_url", "router_name", "router_iface"):
            if not getattr(cur, attr) and getattr(prev, attr):
                setattr(cur, attr, getattr(prev, attr))
                touched = True
        if cur.device_type == "unknown" and prev.device_type != "unknown":
            cur.device_type = prev.device_type
            touched = True
        if prev.trusted and not cur.trusted:
            cur.trusted = True
            touched = True
        if prev.first_seen and (not cur.first_seen or prev.first_seen < cur.first_seen):
            cur.first_seen = prev.first_seen
        if touched:
            count += 1
    return count
