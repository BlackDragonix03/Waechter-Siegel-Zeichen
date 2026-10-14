"""Gespeicherte Scans: laden, vergleichen, umbenennen, löschen, exportieren."""
from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QLabel,
                               QAbstractItemView, QInputDialog, QMessageBox, QFileDialog, QSplitter)

from .. import storage
from ..model import Scan, DeviceDiff, STATUS_NEW, STATUS_MISSING, STATUS_CHANGED
from ..classify import type_icon

STATUS_COLORS = {STATUS_NEW: "#2ee6a6", STATUS_MISSING: "#ff5c5c", STATUS_CHANGED: "#ffb347"}


class HistoryPanel(QWidget):
    load_requested = Signal(object)       # Path
    compare_requested = Signal(object)    # Path
    merge_requested = Signal(object)      # Path

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("Gespeicherte Scans. „Anzeigen“ lädt einen alten Scan, „Vergleichen“ legt ihn über den aktuellen Scan "
                      "(neu / geändert / fehlt), „Werte übernehmen“ ergänzt fehlende Namen und Typen aus dem alten Scan.")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        split = QSplitter(Qt.Orientation.Vertical)
        lay.addWidget(split, 1)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        btns = QHBoxLayout()
        self.btn_show = QPushButton("Anzeigen")
        self.btn_compare = QPushButton("Mit aktuellem Scan vergleichen")
        self.btn_compare.setObjectName("primary")
        self.btn_merge = QPushButton("Werte übernehmen")
        self.btn_rename = QPushButton("Umbenennen")
        self.btn_export = QPushButton("Exportieren (CSV/JSON)")
        self.btn_delete = QPushButton("Löschen")
        self.btn_delete.setObjectName("danger")
        self.btn_refresh = QPushButton("↻")
        for b in (self.btn_show, self.btn_compare, self.btn_merge, self.btn_rename, self.btn_export, self.btn_delete):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(self.btn_refresh)
        tl.addLayout(btns)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Zeitpunkt", "Name", "Ziele", "Geräte", "Probleme"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 260)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(lambda _i: self._emit(self.load_requested))
        tl.addWidget(self.table, 1)
        split.addWidget(top)

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        self.diff_title = QLabel("Vergleich: –")
        self.diff_title.setObjectName("dim")
        bl.addWidget(self.diff_title)
        self.diff = QTableWidget(0, 5)
        self.diff.setHorizontalHeaderLabels(["Status", "Gerät", "IP", "MAC", "Änderungen"])
        self.diff.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.diff.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.diff.verticalHeader().setVisible(False)
        self.diff.horizontalHeader().setStretchLastSection(True)
        self.diff.setColumnWidth(0, 100)
        self.diff.setColumnWidth(1, 220)
        self.diff.setColumnWidth(2, 130)
        self.diff.setColumnWidth(3, 150)
        self.diff.setAlternatingRowColors(True)
        bl.addWidget(self.diff, 1)
        split.addWidget(bottom)
        split.setSizes([300, 300])

        self.btn_show.clicked.connect(lambda: self._emit(self.load_requested))
        self.btn_compare.clicked.connect(lambda: self._emit(self.compare_requested))
        self.btn_merge.clicked.connect(lambda: self._emit(self.merge_requested))
        self.btn_rename.clicked.connect(self._rename)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_export.clicked.connect(self._export)
        self.btn_refresh.clicked.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        items = storage.list_scans()
        self.table.setRowCount(0)
        for path, info in items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            cells = [info["started"].replace("T", " "), info["name"], ", ".join(info["targets"]), str(info["device_count"]), str(info["problem_count"])]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, str(path))
                self.table.setItem(r, c, it)
        if items:
            self.table.selectRow(0)

    def selected_path(self) -> Path | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return Path(self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole))

    def _emit(self, sig) -> None:
        p = self.selected_path()
        if p is not None:
            sig.emit(p)

    def _rename(self) -> None:
        p = self.selected_path()
        if p is None:
            return
        scan = storage.load_scan(p)
        name, ok = QInputDialog.getText(self, "Scan umbenennen", "Name:", text=scan.name)
        if ok:
            scan.name = name.strip()
            storage.save_scan(scan, p)
            self.refresh()

    def _delete(self) -> None:
        p = self.selected_path()
        if p is None:
            return
        if QMessageBox.question(self, "Scan löschen", f"Diesen gespeicherten Scan wirklich löschen?\n{p.name}") == QMessageBox.StandardButton.Yes:
            storage.delete_scan(p)
            self.refresh()

    def _export(self) -> None:
        p = self.selected_path()
        if p is None:
            return
        scan = storage.load_scan(p)
        export_scan_dialog(self, scan)

    def show_diff(self, title: str, diffs: list[DeviceDiff]) -> None:
        self.diff_title.setText(title)
        self.diff.setRowCount(0)
        order = {STATUS_NEW: 0, STATUS_CHANGED: 1, STATUS_MISSING: 2}
        for df in sorted(diffs, key=lambda x: (order.get(x.status, 3), x.device.ip_int())):
            d = df.device
            r = self.diff.rowCount()
            self.diff.insertRow(r)
            cells = [df.status, f"{type_icon(d.device_type)} {d.display_name}", d.ip, d.mac, "; ".join(df.changes)]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c == 0 and df.status in STATUS_COLORS:
                    from PySide6.QtGui import QColor
                    it.setForeground(QColor(STATUS_COLORS[df.status]))
                self.diff.setItem(r, c, it)


def export_scan_dialog(parent: QWidget, scan: Scan) -> None:
    path, flt = QFileDialog.getSaveFileName(parent, "Scan exportieren", f"netguard_{scan.started.replace(':', '-')}",
                                            "CSV-Tabelle (*.csv);;JSON (*.json)")
    if not path:
        return
    try:
        if path.lower().endswith(".json") or "JSON" in flt and not path.lower().endswith(".csv"):
            if not path.lower().endswith(".json"):
                path += ".json"
            storage.save_scan(scan, Path(path))
        else:
            if not path.lower().endswith(".csv"):
                path += ".csv"
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh, delimiter=";")
                w.writerow(["Name", "IP", "MAC", "Hersteller", "Typ", "DNS", "NetBIOS", "mDNS", "UPnP", "Modell", "Ports", "ms", "Subnetz", "Gateway", "Zugang", "Bekannt", "Notiz", "Zuletzt gesehen"])
                for d in scan.sorted_devices():
                    from ..classify import type_label
                    w.writerow([d.display_name, d.ip, d.mac, d.vendor, type_label(d.device_type), d.hostname, d.netbios_name, d.mdns_name,
                                d.ssdp_name, d.ssdp_model, " ".join(map(str, d.open_ports)), "" if d.latency_ms is None else f"{d.latency_ms:.1f}",
                                d.subnet, "ja" if d.is_gateway else "", d.admin_url, "ja" if d.trusted else "", d.note, d.last_seen])
    except OSError as exc:
        QMessageBox.warning(parent, "Export fehlgeschlagen", str(exc))
