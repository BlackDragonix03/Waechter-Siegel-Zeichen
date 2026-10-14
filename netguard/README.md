# NetGuard – Netzwerk-Scanner, Topologie und Diagnose

Ein Werkzeug für Windows (läuft auch unter Linux/macOS), das das eigene Netzwerk durchsucht
und alles zeigt, was man zur Fehlersuche braucht:

- **Full Scan ohne Zielangabe**: Die Subnetz-Suche prüft alle privaten Bereiche (192.168.x.x,
  172.16–31.x.x, 10.x.x.x) auf versteckte Subnetze. Pro möglichem /24 werden nur die typischen
  Router-Adressen .1, .254 und .2 angepingt; antwortet eine, wird das Subnetz komplett gescannt.
  Hinweise aus Routing-Tabelle, ARP-Tabelle und Traceroute werden zuerst geprüft. Stufe „schnell“:
  rund 8.000 Subnetze in etwa einer Minute; „vollständig“: zusätzlich 10.0.0.0/8 komplett
  (rund 70.000 Subnetze, 3 bis 10 Minuten). Gefundene Netze erscheinen in Topologie, Diagnose und
  werden als Ziele übernommen.
- **Geräte finden**: ICMP-Ping, ARP (unter Windows direkt per `SendARP`, findet auch Geräte,
  die Ping blockieren), TCP-Probe, UPnP/SSDP. Mehrere Subnetze und Bereiche gleichzeitig
  (`192.168.178.0/24, 10.0.0.1-50`).
- **Angaben pro Gerät**: IP, MAC, Hersteller (eingebaute OUI-Liste, erweiterbar), Namen
  (DNS, Windows/NetBIOS, Bonjour/mDNS, UPnP), Modell (UPnP), offene Ports mit Dienstnamen,
  HTTP-Titel der Weboberfläche, Antwortzeit, Gerätetyp (Router, PC, Handy, Drucker, Kamera,
  TV, NAS, IoT …), **Zugangs-URL** zur Weboberfläche (Router, NAS, Drucker, Kamera).
- **Topologie**: zoombare Karte (Mausrad, Ziehen, Einpassen, Export als PNG). Router in der Mitte,
  Internet-Pfad, fremde Subnetze über Traceroute-Hops, Knoten frei verschiebbar.
- **Verlauf und Vergleich**: jeder Scan wird gespeichert. Alte Scans anzeigen, über den aktuellen
  legen (neu / geändert / fehlt farbig in Topologie und Liste) oder fehlende Werte aus einem
  alten Scan übernehmen. Eigene Namen, Notizen und „bekannt“-Markierung bleiben über die MAC
  dauerhaft gespeichert. Nach jedem Scan automatischer Vergleich mit dem letzten Scan.
- **Diagnose**: erkennt keine IP (APIPA), fehlendes/totes Gateway, DNS-Fehler, kein Internet,
  doppeltes NAT, hohe Latenz zum Router, unbekannte Geräte, Telnet offen u. a., jeweils mit
  Lösungsvorschlag.
- **Live & Router**: Überwachung aller Geräte (online/offline, Verfügbarkeit, Antwortzeit),
  Router-WAN-Zähler per UPnP (Gesamtverkehr, aktuelle Rate mit Verlaufsgrafik, Uptime, externe IP),
  Geräteliste der Fritz!Box per TR-064 (aktiv, LAN/WLAN, Link-Geschwindigkeit, Signal), SNMP-Zähler
  pro Port für Switches/NAS/Router.
- **Werkzeuge**: Dauer-Ping, Traceroute, Port-Check, Namensauflösung.

## Exe bauen (Windows)

Doppelklick auf **`build-netguard-exe.bat`** im Hauptordner des Repositorys.
Braucht nur Python 3.10 oder neuer (https://www.python.org, „Add python.exe to PATH“ anhaken).
Das Skript legt eine virtuelle Umgebung an, lädt PySide6 und PyInstaller, führt die Tests aus
und baut `release\NetGuard.exe` (eine Datei, ohne Installation). Beim ersten Mal dauert das
einige Minuten und lädt einige hundert MB.

Daten (Scans, bekannte Geräte, Einstellungen) liegen neben der Exe im Ordner `NetGuard-Daten`,
beim Start aus dem Quelltext unter `%APPDATA%\NetGuard`. Mit der Umgebungsvariable
`NETGUARD_DATA` lässt sich der Ordner umbiegen.

## Aus dem Quelltext starten

```
cd netguard
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python netguard.py
```

Tests: `python -m unittest discover -s tests`

## Hinweise

- Kein Admin nötig. Windows-Firewall beim ersten Start für private Netze zulassen, sonst fehlen
  UPnP-, NetBIOS- und mDNS-Antworten.
- Smartphones nutzen oft zufällige MAC-Adressen; dann ist kein Hersteller erkennbar und die
  Wiedererkennung kann sich ändern (im Handy für das Heim-WLAN abschaltbar).
- Vollständige Herstellerliste: `oui.txt` von https://standards-oui.ieee.org/oui/oui.txt neben die
  Exe (oder in den Datenordner) legen; sie wird beim Start eingelesen.
- Router-Abfragen: UPnP am Router einschalten (Fritz!Box: Heimnetz → Netzwerk →
  Netzwerkeinstellungen → „Statusinformationen über UPnP übertragen“). Für die Geräteliste per
  TR-064 zusätzlich „Zugriff für Anwendungen zulassen“ und einen Router-Benutzer mit Passwort.
  Das Passwort wird in `einstellungen.json` im Datenordner im Klartext abgelegt.
- Per-Gerät-Datenmengen liefern Heimrouter über keine Schnittstelle; möglich sind Gesamtverkehr
  (UPnP), aktiv/Link-Rate pro Gerät (TR-064) und Zähler pro Switch-Port (SNMP).
