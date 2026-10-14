"""Detailansicht und Bearbeitung eines Geräts."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
                               QTextEdit, QFormLayout, QScrollArea, QFrame, QGroupBox)

from ..model import Device
from ..classify import type_label, type_icon, TYPES
from . import theme


class DetailsPanel(QWidget):
    saved = Signal(object)            # Device nach Bearbeitung
    open_url = Signal(str)
    tool_requested = Signal(str, str)  # (werkzeug, ip)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device: Device | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self.title = QLabel("Kein Gerät ausgewählt")
        self.title.setObjectName("title")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.subtitle = QLabel("Klicke in der Topologie oder in der Liste auf ein Gerät.")
        self.subtitle.setObjectName("dim")
        self.subtitle.setWordWrap(True)
        lay.addWidget(self.subtitle)

        btns = QHBoxLayout()
        self.btn_open = QPushButton("🌐 Weboberfläche öffnen")
        self.btn_open.clicked.connect(lambda: self.open_url.emit(self.device.admin_url if self.device else ""))
        btns.addWidget(self.btn_open)
        self.btn_ping = QPushButton("Ping")
        self.btn_ping.clicked.connect(lambda: self._tool("ping"))
        btns.addWidget(self.btn_ping)
        self.btn_trace = QPushButton("Pfad")
        self.btn_trace.clicked.connect(lambda: self._tool("trace"))
        btns.addWidget(self.btn_trace)
        self.btn_ports = QPushButton("Ports")
        self.btn_ports.clicked.connect(lambda: self._tool("ports"))
        btns.addWidget(self.btn_ports)
        lay.addLayout(btns)

        info_box = QGroupBox("Erkannte Angaben")
        self.form = QFormLayout(info_box)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form.setHorizontalSpacing(12)
        self.fields: dict[str, QLabel] = {}
        for key, label in (("ip", "IP-Adresse"), ("mac", "MAC-Adresse"), ("vendor", "Hersteller"), ("type", "Gerätetyp"),
                           ("hostname", "DNS-Name"), ("netbios", "Windows-Name"), ("mdns", "Bonjour-Name"), ("ssdp", "UPnP-Name"),
                           ("model", "Modell"), ("subnet", "Subnetz"), ("iface", "Schnittstelle"), ("latency", "Antwortzeit"),
                           ("via", "Erkannt über"), ("hops", "Pfad (Router)"), ("admin", "Zugang"), ("seen", "Gesehen"),
                           ("online", "Live-Status"), ("router", "Laut Router")):
            w = QLabel("–")
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            w.setWordWrap(True)
            w.setOpenExternalLinks(False)
            self.fields[key] = w
            self.form.addRow(label + ":", w)
        lay.addWidget(info_box)

        ports_box = QGroupBox("Dienste / offene Ports")
        pl = QVBoxLayout(ports_box)
        self.ports = QLabel("–")
        self.ports.setWordWrap(True)
        self.ports.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pl.addWidget(self.ports)
        lay.addWidget(ports_box)

        edit_box = QGroupBox("Eigene Angaben (werden für künftige Scans gemerkt)")
        ef = QFormLayout(edit_box)
        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText("z.B. Wohnzimmer-TV")
        ef.addRow("Name:", self.e_name)
        self.e_type = QComboBox()
        for key, (label, icon, _c) in TYPES.items():
            if key not in ("internet",):
                self.e_type.addItem(f"{icon} {label}", key)
        ef.addRow("Typ:", self.e_type)
        self.e_trusted = QCheckBox("Bekanntes, vertrauenswürdiges Gerät")
        ef.addRow("", self.e_trusted)
        self.e_note = QTextEdit()
        self.e_note.setPlaceholderText("Notiz, z.B. Standort, Zugangsdaten-Hinweis, Besonderheiten")
        self.e_note.setFixedHeight(70)
        ef.addRow("Notiz:", self.e_note)
        self.btn_save = QPushButton("Speichern")
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self._save)
        ef.addRow("", self.btn_save)
        lay.addWidget(edit_box)
        lay.addStretch(1)
        self.set_device(None)

    def _tool(self, name: str) -> None:
        if self.device:
            self.tool_requested.emit(name, self.device.ip)

    def set_device(self, d: Device | None) -> None:
        self.device = d
        enabled = d is not None
        for w in (self.btn_ping, self.btn_trace, self.btn_ports, self.btn_save, self.e_name, self.e_type, self.e_trusted, self.e_note):
            w.setEnabled(enabled)
        self.btn_open.setEnabled(bool(d and d.admin_url))
        if d is None:
            self.title.setText("Kein Gerät ausgewählt")
            self.subtitle.setText("Klicke in der Topologie oder in der Liste auf ein Gerät.")
            for w in self.fields.values():
                w.setText("–")
            self.ports.setText("–")
            self.e_name.setText("")
            self.e_note.setPlainText("")
            self.e_trusted.setChecked(False)
            return
        self.title.setText(f"{type_icon(d.device_type)} {d.display_name}")
        sub = type_label(d.device_type)
        if d.is_gateway:
            sub += " · Standard-Gateway"
        if d.is_self:
            sub += " · dieser Computer"
        self.subtitle.setText(sub)
        f = self.fields
        f["ip"].setText(d.ip)
        f["mac"].setText(d.mac or "–")
        f["vendor"].setText(d.vendor or "–")
        f["type"].setText(type_label(d.device_type))
        f["hostname"].setText(d.hostname or "–")
        f["netbios"].setText(d.netbios_name or "–")
        f["mdns"].setText(d.mdns_name or "–")
        f["ssdp"].setText(d.ssdp_name or "–")
        f["model"].setText(d.ssdp_model or "–")
        f["subnet"].setText(d.subnet or "–")
        f["iface"].setText(d.interface or "–")
        f["latency"].setText(f"{d.latency_ms:.1f} ms" if d.latency_ms is not None else "–")
        f["via"].setText(", ".join(d.alive_via) or "–")
        f["hops"].setText(" → ".join(d.hops) if d.hops else "direkt")
        f["admin"].setText(f'<a href="{d.admin_url}" style="color:{theme.ACCENT2}">{d.admin_url}</a>' if d.admin_url else "–")
        f["admin"].setOpenExternalLinks(True)
        seen = d.last_seen.replace("T", " ")
        if d.first_seen and d.first_seen != d.last_seen:
            seen += f"  (zuerst {d.first_seen.replace('T', ' ')})"
        f["seen"].setText(seen or "–")
        f["online"].setText("–" if d.online is None else (f'<span style="color:{theme.OK}">online</span>' if d.online else f'<span style="color:{theme.ERROR}">offline</span>'))
        if d.router_active is None:
            f["router"].setText("– (Reiter „Live & Router“ → Geräteliste)")
        else:
            parts = ["aktiv" if d.router_active else "inaktiv"]
            if d.router_iface:
                parts.append(d.router_iface)
            if d.router_speed_mbps:
                parts.append(f"{d.router_speed_mbps} Mbit/s")
            if d.router_rssi is not None:
                parts.append(f"{d.router_rssi} dBm")
            if d.router_name:
                parts.append(f"Name: {d.router_name}")
            f["router"].setText(" · ".join(parts))
        if d.open_ports:
            lines = []
            for p in d.open_ports:
                lines.append(f"<b>{p}</b> &nbsp; {d.services.get(str(p), '')}")
            self.ports.setText("<br>".join(lines))
        else:
            self.ports.setText("keine offenen Ports gefunden (oder Portprüfung aus)")
        self.e_name.setText(d.custom_name)
        idx = self.e_type.findData(d.device_type)
        self.e_type.setCurrentIndex(idx if idx >= 0 else self.e_type.findData("unknown"))
        self.e_trusted.setChecked(d.trusted)
        self.e_note.setPlainText(d.note)

    def _save(self) -> None:
        if self.device is None:
            return
        d = self.device
        d.custom_name = self.e_name.text().strip()
        d.device_type = self.e_type.currentData() or d.device_type
        d.trusted = self.e_trusted.isChecked()
        d.note = self.e_note.toPlainText().strip()
        self.set_device(d)
        self.saved.emit(d)
