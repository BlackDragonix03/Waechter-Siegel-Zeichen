"""Fehlerdiagnose: erkennt typische Probleme und schlägt Lösungen vor."""
from __future__ import annotations

import ipaddress
from collections import Counter

from .model import Scan

SEV_ERROR = "Fehler"
SEV_WARN = "Warnung"
SEV_INFO = "Hinweis"
SEV_OK = "OK"


def _p(sev: str, title: str, detail: str, solution: str, ip: str = "") -> dict[str, str]:
    return {"severity": sev, "title": title, "detail": detail, "solution": solution, "ip": ip}


def analyze(scan: Scan) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    ifaces = scan.interfaces
    devs = scan.devices
    by_ip = {d.ip: d for d in devs}

    # --- Verbindung / Adresse ---------------------------------------------
    if not ifaces:
        out.append(_p(SEV_ERROR, "Keine Netzwerkverbindung",
                      "Es wurde keine Netzwerkschnittstelle mit IPv4-Adresse gefunden.",
                      "Netzwerkkabel bzw. WLAN prüfen. In Windows: Einstellungen → Netzwerk & Internet → Status."))
    for i in ifaces:
        if i.ip.startswith("169.254."):
            out.append(_p(SEV_ERROR, f"Keine IP-Adresse vom Router erhalten ({i.name})",
                          f"Die Schnittstelle hat die Notfall-Adresse {i.ip} (APIPA). Der DHCP-Server (meist der Router) hat nicht geantwortet.",
                          "Router neu starten, Kabel/WLAN prüfen, danach in der Eingabeaufforderung: ipconfig /release && ipconfig /renew. "
                          "Falls eine feste IP eingetragen ist, diese prüfen."))
        elif not i.gateway:
            out.append(_p(SEV_WARN, f"Kein Standard-Gateway ({i.name})",
                          f"Für {i.ip} ist kein Gateway eingetragen. Über diese Schnittstelle gibt es keinen Weg ins Internet.",
                          "Normal bei reinen Zweit-Netzen (z.B. VM-Adapter). Sonst: DHCP am Router prüfen oder Gateway manuell eintragen."))
    # --- Gateway ------------------------------------------------------------
    for gw in scan.gateways:
        d = by_ip.get(gw)
        if d is None or not any(v in d.alive_via for v in ("icmp", "arp", "tcp", "ssdp")):
            out.append(_p(SEV_ERROR, f"Gateway {gw} antwortet nicht",
                          "Der Router (Standard-Gateway) hat weder auf Ping noch auf ARP geantwortet.",
                          "Router einschalten/neu starten, Kabel und WLAN-Verbindung prüfen. Wenn das WLAN verbunden ist, aber der Router "
                          "nicht antwortet: am Router anmelden und prüfen, ob die Client-Isolierung aktiv ist.", gw))
        elif d.latency_ms is not None and d.latency_ms > 60:
            out.append(_p(SEV_WARN, f"Hohe Laufzeit zum Gateway {gw} ({d.latency_ms:.0f} ms)",
                          "Im lokalen Netz sollte der Router in wenigen Millisekunden antworten. Hohe Werte deuten auf schlechtes WLAN oder Überlast hin.",
                          "Näher an den Router, anderen WLAN-Kanal wählen, 5-GHz-Band nutzen oder Kabel verwenden. Große Downloads anderer Geräte prüfen.", gw))
    # --- DNS / Internet -------------------------------------------------------
    if scan.internet_ok is False:
        if scan.gateways and all(by_ip.get(g) is not None for g in scan.gateways):
            out.append(_p(SEV_ERROR, "Kein Internet, obwohl der Router erreichbar ist",
                          "Verbindungen zu 1.1.1.1 / 8.8.8.8 (Port 443) schlugen fehl.",
                          "Auf der Router-Oberfläche den Internet-Status prüfen (DSL/Kabel/Glasfaser-Sync, Zugangsdaten). "
                          "Router und Modem für 30 Sekunden vom Strom trennen. Störung beim Anbieter prüfen."))
        else:
            out.append(_p(SEV_ERROR, "Kein Internet", "Keine Verbindung nach außen möglich.",
                          "Zuerst die Verbindung zum Router herstellen (siehe oben)."))
    if scan.dns_ok is False and scan.internet_ok:
        dns = sorted({x for i in ifaces for x in i.dns})
        out.append(_p(SEV_ERROR, "Namensauflösung (DNS) funktioniert nicht",
                      f"Internet ist erreichbar, aber Namen wie www.google.com lassen sich nicht auflösen. Eingestellte DNS-Server: {', '.join(dns) or 'keine'}.",
                      "DNS-Server prüfen: In den Adapter-Einstellungen testweise 1.1.1.1 oder 8.8.8.8 eintragen. "
                      "In der Eingabeaufforderung: ipconfig /flushdns. Am Router den DNS-Server kontrollieren."))
    # --- Doppeltes NAT --------------------------------------------------------
    private_hops = [h for h in scan.internet_path if _is_private(h)]
    if len(private_hops) >= 2:
        out.append(_p(SEV_WARN, "Doppeltes NAT erkannt",
                      f"Auf dem Weg ins Internet liegen mehrere private Router: {' → '.join(private_hops)}. "
                      "Portfreigaben, Online-Spiele, VPN und manche Smart-Home-Geräte funktionieren dann oft nicht.",
                      "Den vorgeschalteten Router in den Bridge-/Modem-Modus setzen oder den zweiten Router als Access Point betreiben (DHCP aus, LAN-Port statt WAN-Port verwenden)."))
    # --- IP-Konflikte / Auffälligkeiten -----------------------------------------
    macs = Counter(d.mac for d in devs if d.mac and not d.is_self)
    for mac, n in macs.items():
        if n > 1:
            ips = [d.ip for d in devs if d.mac == mac]
            out.append(_p(SEV_INFO, f"Eine MAC-Adresse mit mehreren IPs ({mac})",
                          f"IPs: {', '.join(ips)}. Entweder ein Gerät mit mehreren Adressen (Router, Server, VM-Host) oder ein Proxy-ARP-Gerät.",
                          "Meist harmlos. Bei Verbindungsproblemen einzelner Geräte: DHCP-Reservierungen am Router prüfen.", ips[0]))
    # Unbekannte Geräte (Wächter-Funktion), nur wenn der Benutzer schon Geräte markiert hat
    if any(d.trusted for d in devs):
        unknown = [d for d in devs if not d.trusted and not d.is_self]
        if unknown:
            names = ", ".join(f"{d.display_name} ({d.ip})" for d in unknown[:8]) + (" …" if len(unknown) > 8 else "")
            out.append(_p(SEV_WARN, f"{len(unknown)} nicht als bekannt markierte Geräte",
                          names,
                          "Geräte in der Liste prüfen und als „bekannt“ markieren. Fremde Geräte: WLAN-Passwort ändern, WPS abschalten, Gastnetz für Besucher nutzen.",
                          unknown[0].ip))
    # Unsichere Dienste
    for d in devs:
        if 23 in d.open_ports:
            out.append(_p(SEV_WARN, f"Telnet offen auf {d.display_name} ({d.ip})",
                          "Telnet überträgt Passwörter unverschlüsselt und ist ein beliebtes Einfallstor.",
                          "Telnet im Gerät abschalten (SSH verwenden) oder das Gerät in ein eigenes IoT-/Gast-Netz stellen.", d.ip))
        if d.device_type in ("camera", "iot") and (3389 in d.open_ports or 445 in d.open_ports):
            out.append(_p(SEV_INFO, f"Ungewöhnliche Dienste auf {d.display_name} ({d.ip})",
                          "Ein IoT-Gerät bietet Windows-Dienste (RDP/SMB) an. Entweder falsch erkannt oder ein Windows-Rechner mit IoT-Namen.",
                          "Gerätetyp in den Details korrigieren.", d.ip))
    # Kein Gerät außer uns?
    others = [d for d in devs if not d.is_self]
    if ifaces and not others:
        out.append(_p(SEV_WARN, "Außer diesem Computer wurde kein Gerät gefunden",
                      "Weder der Router noch andere Geräte haben geantwortet.",
                      "Prüfen, ob eine Firewall ausgehende Pings blockiert, ob WLAN-Client-Isolierung aktiv ist oder ob das richtige Subnetz gescannt wurde."))
    # Viele Geräte ohne Namen
    nameless = [d for d in others if not d.any_name and not d.custom_name]
    if len(others) >= 3 and len(nameless) >= max(3, len(others) // 2):
        out.append(_p(SEV_INFO, f"{len(nameless)} Geräte ohne Namen",
                      "Viele Geräte geben keinen Namen preis (kein DNS-Eintrag, kein NetBIOS/mDNS).",
                      "Am Router (z.B. Fritz!Box → Heimnetz) sind die Namen meist sichtbar; hier über „Bearbeiten“ eigene Namen vergeben, sie bleiben für künftige Scans gespeichert."))
    # Private MACs (Smartphones)
    rnd = [d for d in others if d.vendor.startswith("(private") and not d.is_gateway]
    if rnd:
        out.append(_p(SEV_INFO, f"{len(rnd)} Geräte mit zufälliger MAC-Adresse",
                      "Moderne Smartphones nutzen pro WLAN eine Zufalls-MAC; der Hersteller ist dann nicht erkennbar und die Wiedererkennung kann sich ändern.",
                      "Im Smartphone für das Heim-WLAN die Option „private/zufällige Adresse“ abschalten, wenn eine stabile Zuordnung gewünscht ist."))
    if not out:
        out.append(_p(SEV_OK, "Keine Probleme erkannt", "Gateway, DNS und Internet antworten, keine Auffälligkeiten.", ""))
    order = {SEV_ERROR: 0, SEV_WARN: 1, SEV_INFO: 2, SEV_OK: 3}
    out.sort(key=lambda p: order.get(p["severity"], 9))
    return out


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.IPv4Address(ip).is_private
    except ValueError:
        return False
