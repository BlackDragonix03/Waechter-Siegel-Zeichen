"""Gerätetyp aus Hersteller, Ports, Namen und UPnP-Angaben ableiten."""
from __future__ import annotations

import re

from .model import Device

# type -> (deutsche Bezeichnung, Symbol, Farbe)
TYPES: dict[str, tuple[str, str, str]] = {
    "internet":    ("Internet",            "🌐", "#4c8dff"),
    "router":      ("Router / Gateway",    "📡", "#ff8c42"),
    "switch":      ("Switch / Access Point", "🔀", "#ffb347"),
    "server":      ("Server",              "🗄️", "#8e7cff"),
    "nas":         ("NAS / Speicher",      "💾", "#8e7cff"),
    "pc":          ("Computer",            "💻", "#39c6ff"),
    "self":        ("Dieser Computer",     "⭐", "#2ee6a6"),
    "phone":       ("Smartphone / Tablet", "📱", "#ff6bcb"),
    "printer":     ("Drucker / Scanner",   "🖨️", "#c3d0dc"),
    "camera":      ("Kamera",              "📷", "#ff5c5c"),
    "tv":          ("TV / Streaming",      "📺", "#ffd166"),
    "console":     ("Spielkonsole",        "🎮", "#b5e853"),
    "speaker":     ("Lautsprecher / Audio", "🔊", "#f4a261"),
    "iot":         ("Smart-Home / IoT",    "🔌", "#7fd8be"),
    "vm":          ("Virtuelle Maschine",  "🧩", "#9aa5b1"),
    "unknown":     ("Unbekannt",           "❔", "#6f7d8c"),
}


def type_label(t: str) -> str:
    return TYPES.get(t, TYPES["unknown"])[0]


def type_icon(t: str) -> str:
    return TYPES.get(t, TYPES["unknown"])[1]


def type_color(t: str) -> str:
    return TYPES.get(t, TYPES["unknown"])[2]


_VENDOR_RULES: list[tuple[str, str]] = [
    (r"avm|fritz|speedport|telekom|sagemcom|arcadyan|vodafone|technicolor|arris|hitron|compal|sercomm|zyxel|mikrotik|draytek|lancom|bintec", "router"),
    (r"ubiquiti|aruba|ruckus|aerohive|extreme|meraki", "switch"),
    (r"netgear|tp-link(?! tapo)|d-link|linksys|asus(?!tek)|huawei|zte", "router"),
    (r"cisco", "switch"),
    (r"synology|qnap|thecus|western digital|buffalo", "nas"),
    (r"\bhp\b|canon|brother|epson|kyocera|ricoh|lexmark|xerox|konica|oki", "printer"),
    (r"hikvision|dahua|reolink|axis|foscam|ogemray|ring|nest|tapo|kamera|ip-kamera", "camera"),
    (r"apple", "phone"),
    (r"samsung|xiaomi|oneplus|oppo|vivo|realme|motorola|nokia|htc|fairphone", "phone"),
    (r"playstation|nintendo|xbox", "console"),
    (r"sonos|bose|denon|yamaha|teufel", "speaker"),
    (r"roku|\blg\b|philips tv|sony(?! playstation)|chromecast|fire tv|vestel|hisense|tcl", "tv"),
    (r"google|amazon", "iot"),
    (r"espressif|shelly|tuya|hue|signify|philips hue|homematic|eq-3|gardena|miele|bsh|tado|sonoff", "iot"),
    (r"raspberry", "server"),
    (r"vmware|hyper-v|virtualbox|qemu|xen|parallels|docker", "vm"),
    (r"intel|realtek|dell|gigabyte|asrock|msi|lenovo|acer|fujitsu|medion|wistron|compal|quanta|hon hai|foxconn|clevo|gemtek|microsoft", "pc"),
]

_NAME_RULES: list[tuple[str, str]] = [
    (r"fritz|speedport|router|gateway|easybox|connect-box|fritz\.box|vodafone|telekom|unifi|mikrotik|opnsense|pfsense", "router"),
    (r"switch|access-?point|\bap\b|unifi|ubnt|wlan|wifi-repeater|repeater|mesh", "switch"),
    (r"iphone|ipad|android|galaxy|pixel|phone|handy|redmi|oneplus|xiaomi|huawei-|honor", "phone"),
    (r"macbook|imac|mac-mini|mac-studio|desktop|laptop|notebook|\bpc\b|win(?:dows)?|thinkpad|surface|ws-\d|workstation", "pc"),
    (r"printer|drucker|brother|hp[a-z0-9]*|epson|canon|kyocera|mfc|laserjet|officejet|envy|deskjet|pixma", "printer"),
    (r"cam|kamera|camera|reolink|hikvision|dahua|doorbell|ring-", "camera"),
    (r"\btv\b|fernseher|bravia|roku|firetv|fire-tv|chromecast|shield|appletv|apple-tv|android-tv|samsung-tv|lg-|webos", "tv"),
    (r"playstation|ps[345]|xbox|switch-nintendo|nintendo", "console"),
    (r"sonos|echo|alexa|homepod|speaker|lautsprecher|bose|denon|heos", "speaker"),
    (r"shelly|tasmota|esp-|esp_|hue|homematic|tado|sonoff|tuya|smartplug|steckdose|thermostat|wled|zigbee|ikea|tradfri", "iot"),
    (r"nas|synology|diskstation|ds\d{3}|qnap|freenas|truenas|openmediavault|omv", "nas"),
    (r"server|srv|proxmox|esxi|docker|pihole|pi-hole|raspberry|raspi|rpi|homeassistant|home-assistant|hass|nuc|plex|jellyfin|nextcloud", "server"),
    (r"vm-|-vm|virtual", "vm"),
]


def classify(d: Device) -> str:
    """Bestimmt den Gerätetyp. Gateway-Rolle hat Vorrang."""
    if d.is_self:
        return "self"
    if d.is_gateway:
        return "router"

    ports = set(d.open_ports)
    text = " ".join(x.lower() for x in (d.ssdp_type, d.ssdp_model, d.ssdp_name))
    # Nur der eigentliche Name, ohne Domäne (sonst macht ".fritz.box" jedes Gerät zum Router)
    names = " ".join(x.lower().split(".")[0] for x in (d.hostname, d.netbios_name, d.mdns_name) if x)
    vendor = d.vendor.lower()

    # UPnP ist am verlässlichsten
    if "internetgatewaydevice" in text or "wanconnectiondevice" in text:
        return "router"
    if "wlanaccesspoint" in text or "wfadevice" in text and "mediarenderer" not in text:
        return "switch"
    if "printer" in text:
        return "printer"
    if "mediarenderer" in text or "mediaserver" in text:
        if re.search(r"sonos|speaker|heos|denon|yamaha|bose", text):
            return "speaker"
        if re.search(r"tv|bravia|roku|shield|chromecast|fire", text):
            return "tv"
        if re.search(r"synology|qnap|nas|diskstation", text):
            return "nas"
        if "mediaserver" in text and ("windows" in text or "twonky" in text or "plex" in text):
            return "pc" if "windows" in text else "server"
        return "tv" if "mediarenderer" in text else "server"
    if re.search(r"camera|ipcam|nvr", text):
        return "camera"

    # Ports mit eindeutigen Diensten
    if ports & {9100, 631, 515}:
        return "printer"
    if 554 in ports and not (ports & {445, 3389, 22}):
        return "camera"
    if ports & {5000, 5001} and re.search(r"synology", vendor + names + text):
        return "nas"
    if 3389 in ports or (445 in ports and 135 in ports):
        return "pc"
    if 53 in ports and (80 in ports or 443 in ports) and not (ports & {445, 3389}):
        return "router"

    # Namen (vom Benutzer / Gerät vergebene Namen sind meist aussagekräftig)
    for pat, t in _NAME_RULES:
        if re.search(pat, names):
            return t

    # Hersteller
    for pat, t in _VENDOR_RULES:
        if re.search(pat, vendor):
            if t == "phone" and "apple" in vendor:
                # Apple: Mac oder iPhone? Ports helfen
                if ports & {445, 548, 22, 88, 3283, 5900}:
                    return "pc"
                return "phone"
            if t == "pc" and ports & {22} and not (ports & {445, 3389, 139}):
                return "server"
            return t

    # Restliche Heuristik über Ports
    if 22 in ports and (80 in ports or 443 in ports):
        return "server"
    if 22 in ports:
        return "server"
    if 8009 in ports:
        return "tv"
    if 62078 in ports:
        return "phone"
    if 1400 in ports:
        return "speaker"
    if 80 in ports and len(ports) <= 2:
        return "iot"
    return "unknown"


def admin_url(d: Device) -> str:
    """Zugangs-URL, falls das Gerät eine Weboberfläche anbietet."""
    if d.admin_url:
        return d.admin_url
    ports = d.open_ports
    for p, scheme in ((443, "https"), (80, "http"), (8443, "https"), (8080, "http"), (8000, "http"),
                      (5001, "https"), (5000, "http"), (8006, "https"), (8123, "http"), (9000, "http"),
                      (81, "http"), (631, "http")):
        if p in ports:
            if (scheme == "http" and p == 80) or (scheme == "https" and p == 443):
                return f"{scheme}://{d.ip}/"
            return f"{scheme}://{d.ip}:{p}/"
    if d.ssdp_location:
        m = re.match(r"^(https?://[^/]+)", d.ssdp_location)
        if m:
            return m.group(1) + "/"
    return ""
