"""Hauptfenster: Scan steuern, Topologie, Geräte, Verlauf, Diagnose, Werkzeuge."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices, QKeySequence, QGuiApplication
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QLineEdit, QPushButton, QLabel,
                               QComboBox, QCheckBox, QTabWidget, QDockWidget, QProgressBar, QStatusBar, QMessageBox,
                               QFileDialog, QMenu, QSizePolicy)

from .. import __version__, APP_NAME, storage
from ..model import Scan, Device, DeviceDiff, compare_scans, merge_previous_values, STATUS_NEW, STATUS_MISSING, STATUS_CHANGED
from ..net import local
from ..net.engine import ScanOptions
from .. import diagnostics
from .worker import ScanWorker
from .topology import TopologyView
from .devices import DeviceTable
from .details import DetailsPanel
from .history import HistoryPanel, export_scan_dialog
from .diag import DiagnosticsPanel
from .tools import ToolsPanel
from .live import LivePanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} – Netzwerk-Scanner, Topologie und Diagnose")
        self.resize(1480, 900)
        self.scan: Scan | None = None
        self.compare_with: Scan | None = None
        self.diffs: list[DeviceDiff] | None = None
        self.worker: ScanWorker | None = None
        self.known = storage.load_known()
        self.settings = storage.load_settings()
        self._live: dict[str, Device] = {}

        self._build_toolbar()
        self._build_central()
        self._build_dock()
        self._build_statusbar()
        self._restore_settings()
        QTimer.singleShot(50, self._detect_targets_if_empty)

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("Scan")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        self.btn_scan = QPushButton("▶  Scan starten")
        self.btn_scan.setObjectName("primary")
        self.btn_scan.setShortcut(QKeySequence("F5"))
        self.btn_scan.clicked.connect(self.start_scan)
        tb.addWidget(self.btn_scan)
        self.btn_full = QPushButton("🔍  Full Scan")
        self.btn_full.setToolTip("Sucht ohne Zielangabe alle privaten Bereiche (192.168.x.x, 172.16-31.x.x, 10.x.x.x) nach versteckten Subnetzen\n"
                                 "und scannt alle gefundenen Subnetze komplett. Dauert je nach Stufe 1 bis 10 Minuten.")
        self.btn_full.clicked.connect(self.start_full_scan)
        tb.addWidget(self.btn_full)
        self.btn_stop = QPushButton("■  Stopp")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_scan)
        tb.addWidget(self.btn_stop)
        tb.addSeparator()
        tb.addWidget(QLabel("Ziele:"))
        self.targets = QLineEdit()
        self.targets.setPlaceholderText("z.B. 192.168.178.0/24, 10.0.0.1-50, 192.168.2.0/24  (leer = automatisch)")
        self.targets.setMinimumWidth(360)
        self.targets.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.targets.returnPressed.connect(self.start_scan)
        tb.addWidget(self.targets)
        self.btn_auto = QPushButton("Auto")
        self.btn_auto.setToolTip("Eigene Subnetze automatisch eintragen")
        self.btn_auto.clicked.connect(self._detect_targets)
        tb.addWidget(self.btn_auto)
        tb.addSeparator()
        self.btn_save = QPushButton("💾 Speichern")
        self.btn_save.clicked.connect(self.save_scan)
        tb.addWidget(self.btn_save)
        self.btn_open = QPushButton("📂 Öffnen")
        self.btn_open.clicked.connect(self.open_scan_file)
        tb.addWidget(self.btn_open)
        self.btn_export = QPushButton("⇩ Export")
        self.btn_export.clicked.connect(self.export_current)
        tb.addWidget(self.btn_export)

        self.addToolBarBreak()
        tb = QToolBar("Optionen")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addWidget(QLabel("Ports:"))
        self.port_mode = QComboBox()
        self.port_mode.addItem("schnell (17 Ports)", "quick")
        self.port_mode.addItem("ausführlich (alle bekannten)", "full")
        self.port_mode.addItem("keine", "none")
        tb.addWidget(self.port_mode)
        self.chk_names = QCheckBox("Namen")
        self.chk_names.setChecked(True)
        self.chk_names.setToolTip("DNS, Windows-Namen (NetBIOS) und Bonjour (mDNS) abfragen")
        tb.addWidget(self.chk_names)
        self.chk_upnp = QCheckBox("UPnP")
        self.chk_upnp.setChecked(True)
        self.chk_upnp.setToolTip("Router, Fernseher, NAS usw. über UPnP erkennen (liefert Modell und Namen)")
        tb.addWidget(self.chk_upnp)
        self.chk_trace = QCheckBox("Pfade")
        self.chk_trace.setChecked(True)
        self.chk_trace.setToolTip("Traceroute ins Internet und zu fremden Subnetzen (für die Topologie)")
        tb.addWidget(self.chk_trace)
        self.chk_compare = QCheckBox("Mit letztem Scan vergleichen")
        self.chk_compare.setChecked(True)
        self.chk_compare.setToolTip("Nach dem Scan automatisch neue, geänderte und fehlende Geräte markieren")
        tb.addWidget(self.chk_compare)
        tb.addSeparator()
        tb.addWidget(QLabel("Subnetz-Suche:"))
        self.discover_mode = QComboBox()
        self.discover_mode.addItem("aus (nur Ziele)", "none")
        self.discover_mode.addItem("schnell: 192.168.*, 172.16-31.*, gängige 10.*", "quick")
        self.discover_mode.addItem("vollständig: zusätzlich 10.0.0.0/8 komplett", "full")
        self.discover_mode.setToolTip("Prüft in jedem möglichen /24 die Adressen .1, .254 und .2. Antwortet eine, wird das Subnetz komplett gescannt.\n"
                                      "Hinweise aus Routing-Tabelle, ARP-Tabelle und Traceroute werden immer zuerst geprüft.")
        tb.addWidget(self.discover_mode)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tb.addWidget(spacer)
        self.version_label = QLabel(f"{APP_NAME} {__version__}")
        self.version_label.setObjectName("dim")
        tb.addWidget(self.version_label)

    def _build_central(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Topologie
        topo_host = QWidget()
        tl = QVBoxLayout(topo_host)
        tl.setContentsMargins(6, 6, 6, 6)
        bar = QHBoxLayout()
        self.topo_info = QLabel("")
        self.topo_info.setObjectName("dim")
        bar.addWidget(self.topo_info, 1)
        b_fit = QPushButton("⤢ Einpassen")
        b_in = QPushButton("＋")
        b_out = QPushButton("－")
        b_png = QPushButton("🖼 Als Bild speichern")
        b_relayout = QPushButton("↻ Neu anordnen")
        for b in (b_fit, b_in, b_out, b_relayout, b_png):
            bar.addWidget(b)
        tl.addLayout(bar)
        self.topology = TopologyView()
        tl.addWidget(self.topology, 1)
        b_fit.clicked.connect(self.topology.fit)
        b_in.clicked.connect(self.topology.zoom_in)
        b_out.clicked.connect(self.topology.zoom_out)
        b_relayout.clicked.connect(lambda: self.topology.set_scan(self.scan, self.diffs))
        b_png.clicked.connect(self.export_png)
        self.topology.node_selected.connect(self._select_device)
        self.topology.node_activated.connect(self._open_device_url)
        self.topology.node_context.connect(self._context_menu)
        self.tabs.addTab(topo_host, "🗺  Topologie")

        # Geräte
        self.devices = DeviceTable()
        self.devices.device_selected.connect(self._select_device)
        self.devices.device_activated.connect(self._open_device_url)
        self.devices.context_requested.connect(self._context_menu)
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.devices)
        self.tabs.addTab(host, "📋  Geräte")

        # Verlauf
        self.history = HistoryPanel()
        self.history.load_requested.connect(self.load_saved)
        self.history.compare_requested.connect(self.compare_saved)
        self.history.merge_requested.connect(self.merge_saved)
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.history)
        self.tabs.addTab(host, "🕘  Verlauf && Vergleich")

        # Diagnose
        self.diag = DiagnosticsPanel()
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.diag)
        self.tabs.addTab(host, "🩺  Diagnose")

        # Live & Router
        self.live = LivePanel()
        self.live.devices_updated.connect(self._live_updated)
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.live)
        self.tabs.addTab(host, "📶  Live && Router")

        # Werkzeuge
        self.tools = ToolsPanel()
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.tools)
        self.tabs.addTab(host, "🧰  Werkzeuge")

    def _build_dock(self) -> None:
        self.details = DetailsPanel()
        self.details.saved.connect(self._device_saved)
        self.details.open_url.connect(self._open_url)
        self.details.tool_requested.connect(self._run_tool)
        dock = QDockWidget("Gerätedetails", self)
        dock.setObjectName("details")
        dock.setWidget(self.details)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setMinimumWidth(360)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.dock = dock

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_label = QLabel("Bereit.")
        sb.addWidget(self.status_label, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setVisible(False)
        sb.addPermanentWidget(self.progress)
        self.data_label = QLabel(f"Daten: {storage.data_dir()}")
        self.data_label.setObjectName("dim")
        sb.addPermanentWidget(self.data_label)

    # ------------------------------------------------------------------
    # Einstellungen
    # ------------------------------------------------------------------
    def _restore_settings(self) -> None:
        s = self.settings
        if s.get("targets"):
            self.targets.setText(s["targets"])
        idx = self.port_mode.findData(s.get("port_mode", "quick"))
        if idx >= 0:
            self.port_mode.setCurrentIndex(idx)
        self.chk_names.setChecked(s.get("names", True))
        self.chk_upnp.setChecked(s.get("upnp", True))
        self.chk_trace.setChecked(s.get("trace", True))
        self.chk_compare.setChecked(s.get("compare", True))
        idx = self.discover_mode.findData(s.get("discover", "none"))
        if idx >= 0:
            self.discover_mode.setCurrentIndex(idx)
        self.live.router_ip.setText(s.get("router_ip", ""))
        self.live.tr_user.setText(s.get("tr064_user", ""))
        self.live.tr_pass.setText(s.get("tr064_password", ""))
        self.live.snmp_comm.setText(s.get("snmp_community", "public"))
        if s.get("geometry"):
            try:
                from PySide6.QtCore import QByteArray
                self.restoreGeometry(QByteArray.fromBase64(s["geometry"].encode()))
            except Exception:
                pass

    def closeEvent(self, event) -> None:
        self.live.shutdown()
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        self.settings.update({
            "targets": self.targets.text(),
            "port_mode": self.port_mode.currentData(),
            "names": self.chk_names.isChecked(),
            "upnp": self.chk_upnp.isChecked(),
            "trace": self.chk_trace.isChecked(),
            "compare": self.chk_compare.isChecked(),
            "discover": self.discover_mode.currentData(),
            "router_ip": self.live.router_ip.text().strip(),
            "tr064_user": self.live.tr_user.text().strip(),
            "tr064_password": self.live.tr_pass.text(),
            "snmp_community": self.live.snmp_comm.text().strip(),
            "geometry": bytes(self.saveGeometry().toBase64()).decode(),
        })
        storage.save_settings(self.settings)
        super().closeEvent(event)

    def _detect_targets_if_empty(self) -> None:
        if not self.targets.text().strip():
            self._detect_targets()

    def _detect_targets(self) -> None:
        ifaces = local.interfaces()
        targets = local.default_targets(ifaces)
        self.targets.setText(", ".join(targets))
        gws = local.gateways(ifaces)
        self.status_label.setText(f"Eigene Subnetze: {', '.join(targets) or 'keine'} · Gateway: {', '.join(gws) or 'keins'}")

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    def _options(self) -> ScanOptions:
        targets = [t.strip() for t in self.targets.text().replace(";", ",").split(",") if t.strip()]
        return ScanOptions(
            targets=targets,
            resolve_names=self.chk_names.isChecked(),
            netbios=self.chk_names.isChecked(),
            mdns=self.chk_names.isChecked(),
            port_mode=self.port_mode.currentData() or "quick",
            upnp=self.chk_upnp.isChecked(),
            traceroute=self.chk_trace.isChecked(),
            discover=self.discover_mode.currentData() or "none",
        )

    def start_full_scan(self) -> None:
        """Full Scan: eigene Subnetze plus Suche nach versteckten Subnetzen, ohne Zielangabe."""
        mode = self.discover_mode.currentData()
        if mode == "none":
            idx = self.discover_mode.findData("quick")
            self.discover_mode.setCurrentIndex(idx)
            mode = "quick"
        if mode == "full":
            if QMessageBox.question(self, "Vollständiger Full Scan",
                                    "Es werden rund 70.000 mögliche Subnetze geprüft (etwa 140.000 Pings). Das dauert meist 3 bis 10 Minuten.\n"
                                    "Die Stufe „schnell“ prüft etwa 8.000 Subnetze in rund einer Minute.\n\nVollständig fortfahren?") != QMessageBox.StandardButton.Yes:
                return
        self.targets.setText("")
        self.start_scan(force_discover=True)

    def start_scan(self, force_discover: bool = False) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        opts = self._options()
        if force_discover and opts.discover == "none":
            opts.discover = "quick"
        if not opts.targets:
            opts.targets = local.default_targets(local.interfaces())
        hosts = local.expand_targets(opts.targets)
        if not hosts and opts.discover == "none":
            QMessageBox.warning(self, "Keine Ziele", "Bitte gültige Ziele eingeben, z.B. 192.168.178.0/24 oder 10.0.0.1-50, oder die Subnetz-Suche einschalten.")
            return
        if len(hosts) > 2048 and opts.discover == "none":
            if QMessageBox.question(self, "Großer Scan", f"{len(hosts)} Adressen werden geprüft. Das kann mehrere Minuten dauern. Fortfahren?") != QMessageBox.StandardButton.Yes:
                return
        self._live = {}
        self.diffs = None
        self.compare_with = None
        self.devices.set_devices([])
        self.btn_scan.setEnabled(False)
        self.btn_full.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_label.setText("Scan läuft …")
        self.worker = ScanWorker(opts, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.device_found.connect(self._on_device_found)
        self.worker.finished_scan.connect(self._on_finished)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def stop_scan(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.status_label.setText("Scan wird abgebrochen …")

    def _on_progress(self, phase: str, done: int, total: int, msg: str) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.progress.setFormat(f"{phase} {done}/{total}")
        self.status_label.setText(f"{phase}: {msg}" if msg else phase)

    def _on_device_found(self, d: Device) -> None:
        storage.apply_known([d], self.known)
        self._live[d.ip] = d
        self.devices.update_device(d)

    def _scan_done_ui(self) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_full.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setVisible(False)

    def _on_cancelled(self) -> None:
        self._scan_done_ui()
        self.status_label.setText(f"Scan abgebrochen. {len(self._live)} Geräte bis dahin gefunden.")

    def _on_failed(self, text: str) -> None:
        self._scan_done_ui()
        self.status_label.setText("Scan fehlgeschlagen.")
        QMessageBox.critical(self, "Scan fehlgeschlagen", text[-3000:])

    def _on_finished(self, scan: Scan) -> None:
        self._scan_done_ui()
        storage.apply_known(scan.devices, self.known)
        for d in scan.devices:
            storage.remember_device(self.known, d)
        storage.save_known(self.known)
        scan.problems = diagnostics.analyze(scan)
        previous = None
        if self.chk_compare.isChecked():
            items = storage.list_scans()
            if items:
                try:
                    previous = storage.load_scan(items[0][0])
                except Exception:
                    previous = None
        if previous is not None:
            merge_previous_values(scan, previous)
            scan.problems = diagnostics.analyze(scan)
        self.scan = scan
        path = storage.save_scan(scan)
        self.history.refresh()
        if previous is not None:
            self._apply_compare(previous)
        else:
            self._show_scan()
        n_new = sum(1 for df in (self.diffs or []) if df.status == STATUS_NEW)
        n_missing = sum(1 for df in (self.diffs or []) if df.status == STATUS_MISSING)
        n_changed = sum(1 for df in (self.diffs or []) if df.status == STATUS_CHANGED)
        msg = f"Fertig: {len(scan.devices)} Geräte in {scan.duration_s:.0f} s · gespeichert als {path.name}"
        if scan.discovered:
            msg += f" · {len(scan.discovered)} versteckte Subnetze: {', '.join(scan.discovered)}"
            self.targets.setText(", ".join(scan.targets))
        if self.diffs is not None:
            msg += f" · neu {n_new}, geändert {n_changed}, fehlt {n_missing}"
        errors = [p for p in scan.problems if p["severity"] == diagnostics.SEV_ERROR]
        if errors:
            msg += f" · {len(errors)} Fehler erkannt (siehe Diagnose)"
        self.status_label.setText(msg)

    # ------------------------------------------------------------------
    # Anzeige
    # ------------------------------------------------------------------
    def _show_scan(self) -> None:
        scan = self.scan
        self.topology.set_scan(scan, self.diffs)
        self.devices.set_devices(scan.devices if scan else [], self.diffs)
        self.diag.set_scan(scan)
        self.live.set_scan(scan)
        if scan is not None:
            info = f"{scan.title} · {len(scan.devices)} Geräte · Ziele: {', '.join(scan.targets)}"
            if self.compare_with is not None:
                info += f" · Vergleich mit {self.compare_with.title}"
            self.topo_info.setText(info)
        else:
            self.topo_info.setText("")
        self.details.set_device(None)

    def _apply_compare(self, previous: Scan) -> None:
        if self.scan is None:
            return
        self.compare_with = previous
        self.diffs = compare_scans(self.scan, previous)
        self._show_scan()
        self.history.show_diff(f"Vergleich: {self.scan.title}  ↔  {previous.title}", self.diffs)

    def _select_device(self, d: Device | None) -> None:
        self.details.set_device(d)

    def _device_saved(self, d: Device) -> None:
        storage.remember_device(self.known, d)
        storage.save_known(self.known)
        self.devices.update_device(d)
        self.topology.refresh_device(d)
        if self.scan is not None:
            self.scan.problems = diagnostics.analyze(self.scan)
            self.diag.set_scan(self.scan)
            try:
                storage.save_scan(self.scan, storage.scan_path(self.scan))
            except OSError:
                pass
        self.status_label.setText(f"Gespeichert: {d.display_name} ({d.ip})")

    def _open_device_url(self, d: Device | None) -> None:
        if d is None:
            return
        if d.admin_url:
            self._open_url(d.admin_url)
        else:
            self.details.set_device(d)
            self.status_label.setText(f"{d.ip}: keine Weboberfläche gefunden.")

    def _open_url(self, url: str) -> None:
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _live_updated(self, devices: list) -> None:
        for d in devices:
            self.devices.update_device(d)
            self.topology.refresh_device(d)
        if self.details.device is not None and any(d is self.details.device for d in devices):
            self.details.set_device(self.details.device)

    def _run_tool(self, tool: str, ip: str) -> None:
        self.tabs.setCurrentIndex(5)
        self.tools.start(tool, ip)

    def _context_menu(self, d: Device | None, pos) -> None:
        if d is None:
            return
        self.details.set_device(d)
        menu = QMenu(self)
        a = menu.addAction(f"🌐 Weboberfläche öffnen ({d.admin_url})" if d.admin_url else "🌐 Keine Weboberfläche gefunden")
        a.setEnabled(bool(d.admin_url))
        a.triggered.connect(lambda: self._open_url(d.admin_url))
        for p, label in ((80, "http"), (443, "https")):
            if p not in d.open_ports:
                act = menu.addAction(f"{label}://{d.ip}/ versuchen")
                act.triggered.connect(lambda _c=False, u=f"{label}://{d.ip}/": self._open_url(u))
        menu.addSeparator()
        menu.addAction("Ping").triggered.connect(lambda: self._run_tool("ping", d.ip))
        menu.addAction("Pfad (Traceroute)").triggered.connect(lambda: self._run_tool("trace", d.ip))
        menu.addAction("Alle Ports prüfen").triggered.connect(lambda: self._run_tool("ports", d.ip))
        menu.addSeparator()
        menu.addAction("IP kopieren").triggered.connect(lambda: QGuiApplication.clipboard().setText(d.ip))
        if d.mac:
            menu.addAction("MAC kopieren").triggered.connect(lambda: QGuiApplication.clipboard().setText(d.mac))
        menu.addSeparator()
        t = menu.addAction("Als bekannt markieren" if not d.trusted else "Markierung „bekannt“ entfernen")

        def toggle():
            d.trusted = not d.trusted
            self.details.set_device(d)
            self._device_saved(d)
        t.triggered.connect(toggle)
        menu.addAction("In Topologie zeigen").triggered.connect(lambda: (self.tabs.setCurrentIndex(0), self.topology.select_ip(d.ip)))
        menu.addAction("In Liste zeigen").triggered.connect(lambda: (self.tabs.setCurrentIndex(1), self.devices.select_ip(d.ip)))
        menu.exec(pos)

    # ------------------------------------------------------------------
    # Speichern / Laden / Vergleichen
    # ------------------------------------------------------------------
    def save_scan(self) -> None:
        if self.scan is None:
            QMessageBox.information(self, "Kein Scan", "Es gibt noch keinen Scan zum Speichern.")
            return
        path = storage.save_scan(self.scan)
        self.history.refresh()
        self.status_label.setText(f"Gespeichert: {path}")

    def export_current(self) -> None:
        if self.scan is None:
            QMessageBox.information(self, "Kein Scan", "Es gibt noch keinen Scan zum Exportieren.")
            return
        export_scan_dialog(self, self.scan)

    def export_png(self) -> None:
        if self.scan is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Topologie als Bild speichern", "netzwerk-topologie.png", "PNG-Bild (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            if self.topology.export_png(path):
                self.status_label.setText(f"Bild gespeichert: {path}")
            else:
                QMessageBox.warning(self, "Fehler", "Das Bild konnte nicht gespeichert werden.")

    def open_scan_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Scan öffnen", str(storage.scans_dir()), "NetGuard-Scan (*.json)")
        if path:
            self.load_saved(Path(path))

    def load_saved(self, path: Path) -> None:
        try:
            scan = storage.load_scan(path)
        except Exception as exc:
            QMessageBox.warning(self, "Laden fehlgeschlagen", str(exc))
            return
        storage.apply_known(scan.devices, self.known)
        if not scan.problems:
            scan.problems = diagnostics.analyze(scan)
        self.scan = scan
        self.diffs = None
        self.compare_with = None
        self._show_scan()
        self.tabs.setCurrentIndex(0)
        self.status_label.setText(f"Geladen: {scan.title} ({len(scan.devices)} Geräte)")

    def compare_saved(self, path: Path) -> None:
        if self.scan is None:
            QMessageBox.information(self, "Kein aktueller Scan", "Zuerst einen Scan starten oder einen Scan anzeigen; danach einen älteren zum Vergleich wählen.")
            return
        try:
            previous = storage.load_scan(path)
        except Exception as exc:
            QMessageBox.warning(self, "Laden fehlgeschlagen", str(exc))
            return
        if previous.id == self.scan.id:
            QMessageBox.information(self, "Gleicher Scan", "Bitte einen anderen Scan zum Vergleich wählen.")
            return
        self._apply_compare(previous)
        self.tabs.setCurrentIndex(0)
        n = {s: sum(1 for df in self.diffs or [] if df.status == s) for s in (STATUS_NEW, STATUS_CHANGED, STATUS_MISSING)}
        self.status_label.setText(f"Vergleich mit {previous.title}: neu {n[STATUS_NEW]}, geändert {n[STATUS_CHANGED]}, fehlt {n[STATUS_MISSING]}")

    def merge_saved(self, path: Path) -> None:
        if self.scan is None:
            QMessageBox.information(self, "Kein aktueller Scan", "Zuerst einen Scan starten oder anzeigen.")
            return
        try:
            previous = storage.load_scan(path)
        except Exception as exc:
            QMessageBox.warning(self, "Laden fehlgeschlagen", str(exc))
            return
        n = merge_previous_values(self.scan, previous)
        self.scan.problems = diagnostics.analyze(self.scan)
        storage.save_scan(self.scan, storage.scan_path(self.scan))
        self._show_scan()
        self.status_label.setText(f"{n} Geräte mit Werten aus {previous.title} ergänzt.")
