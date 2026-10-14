"""Reiter „Live & Router“: Überwachung, Router-Zähler, Geräteliste des Routers, SNMP."""
from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import Qt, Signal, QObject, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QGroupBox,
                               QFormLayout, QTableWidget, QTableWidgetItem, QAbstractItemView, QSplitter, QPlainTextEdit,
                               QCheckBox, QSizePolicy)

from ..model import Device, Scan
from ..classify import type_icon, type_label
from ..net import router as routermod, snmp as snmpmod
from ..net.monitor import Monitor, MonitorSample
from .worker import FuncWorker
from . import theme


class _Bridge(QObject):
    sample = Signal(object)
    error = Signal(str)


class RateGraph(QWidget):
    """Kleine Verlaufsgrafik für Download/Upload (Byte/s)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rx: deque[float] = deque(maxlen=120)
        self.tx: deque[float] = deque(maxlen=120)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def add(self, rx: float | None, tx: float | None) -> None:
        self.rx.append(rx or 0.0)
        self.tx.append(tx or 0.0)
        self.update()

    def clear(self) -> None:
        self.rx.clear()
        self.tx.clear()
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(0, 0, -1, -1)
        p.setPen(QPen(QColor(theme.BORDER)))
        p.setBrush(QColor(theme.BG2))
        p.drawRoundedRect(r, 6, 6)
        if not self.rx:
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Noch keine Router-Daten. Überwachung starten oder Router abfragen.")
            return
        peak = max(max(self.rx), max(self.tx), 1.0)
        inner = QRectF(r).adjusted(8, 18, -8, -8)
        n = self.rx.maxlen or 120
        for data, color in ((self.rx, theme.ACCENT2), (self.tx, theme.WARN)):
            path = QPainterPath()
            for i, v in enumerate(data):
                x = inner.left() + inner.width() * (i + (n - len(data))) / max(n - 1, 1)
                y = inner.bottom() - inner.height() * (v / peak)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(QColor(color), 2))
            p.drawPath(path)
        p.setPen(QColor(theme.TEXT_DIM))
        f = QFont()
        f.setPointSizeF(8)
        p.setFont(f)
        p.drawText(QRectF(r).adjusted(8, 2, -8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                   f"Spitze {routermod.human_rate(peak)}   ▬ Download   ▬ Upload (gelb)")


class LivePanel(QWidget):
    devices_updated = Signal(object)   # list[Device] mit aktualisierten Live-/Router-Feldern

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scan: Scan | None = None
        self.monitor: Monitor | None = None
        self.bridge = _Bridge()
        self.bridge.sample.connect(self._on_sample)
        self.bridge.error.connect(lambda e: self.log.appendPlainText(e))
        self.worker: FuncWorker | None = None
        self._last_wan: routermod.WanStatus | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        lay.addLayout(top)

        # --- Router-Einstellungen -------------------------------------------------
        box = QGroupBox("Router")
        f = QFormLayout(box)
        self.router_ip = QLineEdit()
        self.router_ip.setPlaceholderText("Gateway, z.B. 192.168.178.1")
        f.addRow("IP:", self.router_ip)
        self.tr_user = QLineEdit()
        self.tr_user.setPlaceholderText("Fritz!Box-Benutzer (TR-064)")
        f.addRow("Benutzer:", self.tr_user)
        self.tr_pass = QLineEdit()
        self.tr_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.tr_pass.setPlaceholderText("Passwort")
        f.addRow("Passwort:", self.tr_pass)
        self.snmp_comm = QLineEdit("public")
        f.addRow("SNMP-Community:", self.snmp_comm)
        row = QHBoxLayout()
        self.btn_wan = QPushButton("WAN-Zähler (UPnP)")
        self.btn_wan.setToolTip("Ohne Login: Gesamtverkehr, aktuelle Rate, Uptime, externe IP")
        self.btn_hosts = QPushButton("Geräteliste (TR-064)")
        self.btn_hosts.setToolTip("Mit Login (Fritz!Box): welche Geräte sind laut Router aktiv, Anschluss, Geschwindigkeit, Signal")
        self.btn_snmp = QPushButton("SNMP")
        self.btn_snmp.setToolTip("Schnittstellen-Zähler eines Geräts per SNMP v2c abfragen (Switch, NAS, Router)")
        row.addWidget(self.btn_wan)
        row.addWidget(self.btn_hosts)
        row.addWidget(self.btn_snmp)
        f.addRow("", row)
        top.addWidget(box, 2)

        # --- WAN-Status -------------------------------------------------------------
        box2 = QGroupBox("Internetanschluss (laut Router)")
        f2 = QFormLayout(box2)
        self.wan_fields: dict[str, QLabel] = {}
        for key, label in (("model", "Router"), ("status", "Verbindung"), ("ext", "Externe IP"), ("uptime", "Verbunden seit"),
                           ("link", "Anschluss (max.)"), ("total", "Gesamt seit Verbindung"), ("rate", "Aktuell")):
            w = QLabel("–")
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            w.setWordWrap(True)
            w.setMinimumWidth(260)
            self.wan_fields[key] = w
            f2.addRow(label + ":", w)
        top.addWidget(box2, 3)

        # --- Überwachung -------------------------------------------------------------
        box3 = QGroupBox("Live-Überwachung")
        f3 = QFormLayout(box3)
        self.interval = QComboBox()
        for s in (3, 5, 10, 30, 60):
            self.interval.addItem(f"alle {s} s", s)
        self.interval.setCurrentIndex(1)
        f3.addRow("Intervall:", self.interval)
        self.chk_router = QCheckBox("Router-Zähler mit abfragen")
        self.chk_router.setChecked(True)
        f3.addRow("", self.chk_router)
        self.btn_start = QPushButton("▶ Überwachung starten")
        self.btn_start.setObjectName("primary")
        self.btn_stop = QPushButton("■ Stopp")
        self.btn_stop.setEnabled(False)
        r3 = QHBoxLayout()
        r3.addWidget(self.btn_start)
        r3.addWidget(self.btn_stop)
        f3.addRow("", r3)
        self.mon_status = QLabel("nicht aktiv")
        self.mon_status.setObjectName("dim")
        self.mon_status.setWordWrap(True)
        f3.addRow("Status:", self.mon_status)
        top.addWidget(box3, 2)

        self.graph = RateGraph()
        lay.addWidget(self.graph)

        split = QSplitter(Qt.Orientation.Vertical)
        lay.addWidget(split, 1)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["Gerät", "IP", "MAC", "Online (Ping)", "ms", "Verfügbarkeit", "Aktiv (Router)", "Anschluss", "Link", "Signal"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        for i, w in enumerate((220, 130, 150, 110, 60, 110, 120, 120, 150, 80)):
            self.table.setColumnWidth(i, w)
        split.addWidget(self.table)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)
        self.log.setStyleSheet(f"font-family: Consolas, 'Cascadia Mono', monospace; font-size: 9.5pt; background: {theme.BG2};")
        split.addWidget(self.log)
        split.setSizes([400, 140])

        self.btn_wan.clicked.connect(self.query_wan)
        self.btn_hosts.clicked.connect(self.query_hosts)
        self.btn_snmp.clicked.connect(self.query_snmp)
        self.btn_start.clicked.connect(self.start_monitor)
        self.btn_stop.clicked.connect(self.stop_monitor)

    # ------------------------------------------------------------------
    def set_scan(self, scan: Scan | None) -> None:
        self.scan = scan
        if scan is not None and scan.gateways and not self.router_ip.text().strip():
            self.router_ip.setText(scan.gateways[0])
        self._fill_table()

    def _devices(self) -> list[Device]:
        return list(self.scan.devices) if self.scan else []

    def _fill_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        states = self.monitor.states if self.monitor else {}
        for d in self._devices():
            r = self.table.rowCount()
            self.table.insertRow(r)
            st = states.get(d.ip)
            online = "–" if d.online is None else ("✔ online" if d.online else "✖ offline")
            avail = f"{100 * st.up_count / st.total_count:.0f} %" if st and st.total_count else "–"
            ms = "" if not (st and st.latency_ms is not None) else f"{st.latency_ms:.0f}"
            active = "–" if d.router_active is None else ("✔ ja" if d.router_active else "✖ nein")
            link = f"{d.router_speed_mbps} Mbit/s" if d.router_speed_mbps else ""
            rssi = f"{d.router_rssi} dBm" if d.router_rssi is not None else ""
            name = d.display_name if d.display_name != d.ip else type_label(d.device_type)
            cells = [f"{type_icon(d.device_type)} {name}", d.ip, d.mac, online, ms, avail, active, d.router_iface, link, rssi]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c == 1:
                    it.setData(Qt.ItemDataRole.UserRole, d.ip_int())
                if c == 3:
                    it.setForeground(QColor(theme.OK if d.online else theme.ERROR) if d.online is not None else QColor(theme.TEXT_DIM))
                if c == 6 and d.router_active is not None:
                    it.setForeground(QColor(theme.OK if d.router_active else theme.TEXT_DIM))
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)

    def _router(self) -> str:
        ip = self.router_ip.text().strip()
        if not ip and self.scan and self.scan.gateways:
            ip = self.scan.gateways[0]
            self.router_ip.setText(ip)
        if not ip:
            self.log.appendPlainText("Bitte Router-IP eintragen (zuerst einen Scan starten, dann wird das Gateway übernommen).")
        return ip

    def _run_bg(self, fn) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.log.appendPlainText("Bitte warten, eine Abfrage läuft noch.")
            return
        self.worker = FuncWorker(fn)
        self.worker.line.connect(self.log.appendPlainText)
        self.worker.done.connect(self._bg_done)
        for b in (self.btn_wan, self.btn_hosts, self.btn_snmp):
            b.setEnabled(False)
        self.worker.start()

    def _bg_done(self) -> None:
        for b in (self.btn_wan, self.btn_hosts, self.btn_snmp):
            b.setEnabled(True)
        if self._pending_wan is not None:
            self._show_wan(self._pending_wan)
            self._pending_wan = None
        if self._pending_hosts is not None:
            self._apply_hosts(self._pending_hosts)
            self._pending_hosts = None

    _pending_wan: routermod.WanStatus | None = None
    _pending_hosts: routermod.RouterHosts | None = None

    # ------------------------------------------------------------------
    def query_wan(self) -> None:
        ip = self._router()
        if not ip:
            return

        def job(emit, stopped):
            emit(f"UPnP-Abfrage an {ip} …")
            st = routermod.query_wan(ip)
            self._pending_wan = st
            emit(f"{st.model or 'Router'}: {'OK' if st.ok else st.error}")
        self._run_bg(job)

    def _show_wan(self, st: routermod.WanStatus) -> None:
        f = self.wan_fields
        if not st.ok:
            f["status"].setText(f'<span style="color:{theme.ERROR}">nicht abfragbar</span> (siehe Protokoll unten)')
            self.log.appendPlainText(st.error)
            return
        f["model"].setText(st.model or "–")
        f["status"].setText(st.connection_status or "–")
        f["ext"].setText(st.external_ip or "–")
        f["uptime"].setText(routermod.human_uptime(st.uptime_s))
        link = ""
        if st.link_down_bps:
            link = f"↓ {routermod.human_rate(st.link_down_bps / 8)}"
        if st.link_up_bps:
            link += f"   ↑ {routermod.human_rate(st.link_up_bps / 8)}"
        f["link"].setText(link or "–")
        f["total"].setText(f"↓ {routermod.human_bytes(st.total_rx)}   ↑ {routermod.human_bytes(st.total_tx)}")
        rate = ""
        if st.rate_rx_bps is not None or st.rate_tx_bps is not None:
            rate = f"↓ {routermod.human_rate(st.rate_rx_bps)}   ↑ {routermod.human_rate(st.rate_tx_bps)}"
        f["rate"].setText(rate or "– (erst nach zweiter Abfrage berechenbar)")
        if st.history_rx and not self.graph.rx:
            for rx, tx in zip(reversed(st.history_rx), reversed(st.history_tx or [0] * len(st.history_rx))):
                self.graph.add(float(rx), float(tx))
        elif st.rate_rx_bps is not None:
            self.graph.add(st.rate_rx_bps, st.rate_tx_bps)
        self._last_wan = st

    def query_hosts(self) -> None:
        ip = self._router()
        if not ip:
            return
        user, pw = self.tr_user.text().strip(), self.tr_pass.text()
        if not pw:
            self.log.appendPlainText("TR-064 braucht das Router-Passwort (Fritz!Box: Benutzer und Passwort eines FRITZ!Box-Benutzers, oder nur das Kennwort der Box).")
            return

        def job(emit, stopped):
            emit(f"TR-064-Abfrage an {ip} …")
            res = routermod.query_tr064_hosts(ip, user, pw)
            self._pending_hosts = res
            if res.ok:
                active = sum(1 for h in res.hosts if h.active)
                emit(f"{res.model or 'Router'}: {len(res.hosts)} Geräte bekannt, {active} aktiv.")
            else:
                emit(res.error)
        self._run_bg(job)

    def _apply_hosts(self, res: routermod.RouterHosts) -> None:
        if not res.ok or self.scan is None:
            return
        by_mac = {h.mac: h for h in res.hosts if h.mac}
        by_ip = {h.ip: h for h in res.hosts if h.ip}
        touched: list[Device] = []
        for d in self.scan.devices:
            h = by_mac.get(d.mac.lower()) if d.mac else None
            if h is None:
                h = by_ip.get(d.ip)
            if h is None:
                continue
            d.router_active = h.active
            d.router_iface = _iface_label(h)
            d.router_speed_mbps = h.speed_mbps
            d.router_rssi = h.rssi
            if h.name and not d.router_name:
                d.router_name = h.name
            if not d.mac and h.mac:
                d.mac = h.mac
            touched.append(d)
        # Geräte, die der Router kennt, aber der Scan nicht fand (z.B. abgeschaltet)
        known_ips = {d.ip for d in self.scan.devices}
        extra = [h for h in res.hosts if h.ip and h.ip not in known_ips and h.active]
        for h in extra:
            self.log.appendPlainText(f"Router kennt zusätzlich aktiv: {h.name or '?'} {h.ip} {h.mac} ({_iface_label(h)})")
        self._fill_table()
        self.devices_updated.emit(touched)

    def query_snmp(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        ip = self.table.item(rows[0].row(), 1).text() if rows else self._router()
        comm = self.snmp_comm.text().strip() or "public"
        if not ip:
            return

        def job(emit, stopped):
            emit(f"SNMP-Abfrage an {ip} (Community „{comm}“) …")
            res = snmpmod.query_interfaces(ip, comm, 2.0)
            if not res.ok:
                emit(res.error)
                return
            emit(f"{res.sys_name or ip}: {res.sys_descr[:80]}  Uptime {routermod.human_uptime(res.uptime_s)}")
            for i in res.interfaces:
                state = "up" if i.up else ("down" if i.up is False else "?")
                emit(f"  [{i.index:>3}] {i.name:<24} {state:<5} ↓ {routermod.human_bytes(i.in_octets):>10}   ↑ {routermod.human_bytes(i.out_octets):>10}")
            emit("Hinweis: Zähler sind Gesamtwerte seit Start. Zweite Abfrage später → Differenz = Datenmenge im Zeitraum.")
        self._run_bg(job)

    # ------------------------------------------------------------------
    def start_monitor(self) -> None:
        if self.monitor is not None and self.monitor.running:
            return
        ips = [d.ip for d in self._devices()]
        if not ips:
            self.log.appendPlainText("Kein Scan vorhanden. Zuerst einen Scan starten.")
            return
        router_ip = self.router_ip.text().strip() or (self.scan.gateways[0] if self.scan and self.scan.gateways else "")
        self.monitor = Monitor(ips, float(self.interval.currentData()), router_ip, self.chk_router.isChecked(),
                               on_sample=self.bridge.sample.emit, on_error=self.bridge.error.emit)
        self.monitor.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.mon_status.setText(f"läuft: {len(ips)} Geräte" + (f", Router {router_ip}" if self.chk_router.isChecked() and router_ip else ""))
        self.log.appendPlainText(f"Überwachung gestartet ({len(ips)} Geräte, {self.interval.currentText()}).")

    def stop_monitor(self) -> None:
        if self.monitor is not None:
            self.monitor.stop()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.mon_status.setText("gestoppt")

    def _on_sample(self, s: MonitorSample) -> None:
        if self.scan is None:
            return
        changed: list[Device] = []
        for d in self.scan.devices:
            st = s.hosts.get(d.ip)
            if st is None:
                continue
            was = d.online
            d.online = st.online
            if st.online and st.latency_ms is not None:
                d.latency_ms = st.latency_ms
            if was is not None and was != st.online:
                self.log.appendPlainText(f"{time.strftime('%H:%M:%S')}  {d.display_name} ({d.ip}) ist jetzt {'ONLINE' if st.online else 'OFFLINE'}")
            changed.append(d)
        if s.wan is not None and s.wan.ok:
            s.wan.rate_rx_bps = s.rate_rx_bps if s.rate_rx_bps is not None else s.wan.rate_rx_bps
            s.wan.rate_tx_bps = s.rate_tx_bps if s.rate_tx_bps is not None else s.wan.rate_tx_bps
            self._show_wan(s.wan)
            self.graph.add(s.wan.rate_rx_bps, s.wan.rate_tx_bps)
        elif s.wan is not None and not s.wan.ok and not self._last_wan:
            self.wan_fields["status"].setText(f'<span style="color:{theme.WARN}">nicht abfragbar</span> (Router-Zähler aus oder UPnP am Router gesperrt)')
        online = sum(1 for d in self.scan.devices if d.online)
        self.mon_status.setText(f"läuft · {online}/{len(s.hosts)} online · {time.strftime('%H:%M:%S')}")
        self._fill_table()
        self.devices_updated.emit(changed)

    def shutdown(self) -> None:
        self.stop_monitor()


def _iface_label(h: routermod.RouterHost) -> str:
    t = (h.interface or "").lower()
    if "802.11" in t or "wlan" in t or "wifi" in t:
        label = "WLAN"
    elif "ethernet" in t or t == "lan":
        label = "LAN"
    else:
        label = h.interface or "–"
    if h.port:
        label += f" ({h.port})"
    if h.guest:
        label += " Gast"
    return label
