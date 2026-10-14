"""Geräteliste als sortier- und filterbare Tabelle."""
from __future__ import annotations

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTableView, QLabel, QComboBox, QHeaderView, QAbstractItemView

from ..model import Device, DeviceDiff, STATUS_NEW, STATUS_MISSING, STATUS_CHANGED, STATUS_SAME
from ..classify import type_label, type_icon, TYPES
from . import theme

COLUMNS = ["Status", "Typ", "Name", "IP", "MAC", "Hersteller", "Offene Ports", "ms", "Online", "Router", "Subnetz", "Erkannt über", "Zuletzt gesehen", "Bekannt"]
STATUS_COLORS = {STATUS_NEW: "#2ee6a6", STATUS_MISSING: "#ff5c5c", STATUS_CHANGED: "#ffb347"}


class DeviceTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.rows: list[tuple[Device, str, list[str]]] = []

    def set_devices(self, devices: list[Device], diffs: list[DeviceDiff] | None = None) -> None:
        self.beginResetModel()
        self.rows = []
        if diffs:
            for df in diffs:
                if df.device is not None:
                    self.rows.append((df.device, df.status, df.changes))
        else:
            self.rows = [(d, "", []) for d in devices]
        self.endResetModel()

    def update_device(self, device: Device) -> None:
        for i, (d, st, ch) in enumerate(self.rows):
            if d.ip == device.ip and st != STATUS_MISSING:
                self.rows[i] = (device, st, ch)
                self.dataChanged.emit(self.index(i, 0), self.index(i, len(COLUMNS) - 1))
                return
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        self.rows.append((device, "", []))
        self.endInsertRows()

    def device_at(self, row: int) -> Device | None:
        return self.rows[row][0] if 0 <= row < len(self.rows) else None

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        d, status, changes = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return status or ("" if not d.last_seen else STATUS_SAME if status == STATUS_SAME else "")
            if col == 1:
                return f"{type_icon(d.device_type)} {type_label(d.device_type)}"
            if col == 2:
                name = d.display_name
                return "" if name == d.ip else name
            if col == 3:
                return d.ip
            if col == 4:
                return d.mac
            if col == 5:
                return d.vendor
            if col == 6:
                return ", ".join(map(str, d.open_ports))
            if col == 7:
                return "" if d.latency_ms is None else f"{d.latency_ms:.0f}"
            if col == 8:
                return "–" if d.online is None else ("✔" if d.online else "✖")
            if col == 9:
                if d.router_active is None:
                    return ""
                txt = "aktiv" if d.router_active else "inaktiv"
                if d.router_iface:
                    txt += f" · {d.router_iface}"
                if d.router_speed_mbps:
                    txt += f" · {d.router_speed_mbps} Mbit/s"
                return txt
            if col == 10:
                return d.subnet
            if col == 11:
                return ", ".join(d.alive_via)
            if col == 12:
                return d.last_seen.replace("T", " ")
            if col == 13:
                return "✔" if d.trusted else ""
        if role == Qt.ItemDataRole.UserRole:
            # Sortierschlüssel
            if col == 3:
                return d.ip_int()
            if col == 7:
                return d.latency_ms if d.latency_ms is not None else 1e9
            if col == 0:
                return {STATUS_NEW: 0, STATUS_CHANGED: 1, STATUS_MISSING: 2}.get(status, 3)
            return self.data(index, Qt.ItemDataRole.DisplayRole)
        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 0 and status in STATUS_COLORS:
                return QColor(STATUS_COLORS[status])
            if status == STATUS_MISSING:
                return QColor(theme.TEXT_DIM)
            if col == 13 and d.trusted:
                return QColor(theme.ACCENT)
            if col == 8 and d.online is not None:
                return QColor(theme.OK if d.online else theme.ERROR)
            if col == 1:
                return QColor(TYPES.get(d.device_type, TYPES["unknown"])[2])
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == 0 and changes:
                return "\n".join(changes)
            if col == 6 and d.services:
                return "\n".join(f"{p}: {s}" for p, s in sorted(d.services.items(), key=lambda kv: int(kv[0])))
            if col == 2:
                parts = [f"{k}: {v}" for k, v in (("Eigener Name", d.custom_name), ("DNS", d.hostname), ("NetBIOS", d.netbios_name),
                                                   ("mDNS", d.mdns_name), ("UPnP", d.ssdp_name), ("Modell", d.ssdp_model)) if v]
                return "\n".join(parts) or None
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (7,):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None


class _Proxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.type_filter = ""
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        model: DeviceTableModel = self.sourceModel()  # type: ignore[assignment]
        d = model.device_at(row)
        if d is None:
            return False
        if self.type_filter and d.device_type != self.type_filter:
            return False
        if not self.text:
            return True
        hay = " ".join((d.ip, d.mac, d.vendor, d.hostname, d.netbios_name, d.mdns_name, d.ssdp_name, d.ssdp_model,
                        d.custom_name, d.note, type_label(d.device_type), d.subnet, " ".join(map(str, d.open_ports)),
                        model.rows[row][1])).lower()
        return all(t in hay for t in self.text.lower().split())


class DeviceTable(QWidget):
    device_selected = Signal(object)
    device_activated = Signal(object)
    context_requested = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = DeviceTableModel()
        self.proxy = _Proxy()
        self.proxy.setSourceModel(self.model)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Suchen: Name, IP, MAC, Hersteller, Port …")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        self.type_box = QComboBox()
        self.type_box.addItem("Alle Typen", "")
        for key, (label, icon, _c) in TYPES.items():
            self.type_box.addItem(f"{icon} {label}", key)
        self.type_box.currentIndexChanged.connect(self._filter)
        top.addWidget(self.type_box)
        self.count = QLabel("")
        self.count.setObjectName("badge")
        top.addWidget(self.count)
        lay.addLayout(top)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(28)
        hdr = self.view.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._context)
        self.view.selectionModel().currentRowChanged.connect(self._sel)
        self.view.doubleClicked.connect(lambda idx: self.device_activated.emit(self._dev(idx)))
        lay.addWidget(self.view, 1)
        for i, w in enumerate((90, 170, 190, 120, 140, 160, 170, 50, 60, 170, 130, 110, 140, 70)):
            self.view.setColumnWidth(i, w)

    def _dev(self, idx: QModelIndex) -> Device | None:
        if not idx.isValid():
            return None
        return self.model.device_at(self.proxy.mapToSource(idx).row())

    def _sel(self, cur: QModelIndex, _prev: QModelIndex) -> None:
        self.device_selected.emit(self._dev(cur))

    def _context(self, pos) -> None:
        idx = self.view.indexAt(pos)
        d = self._dev(idx)
        if d is not None:
            self.context_requested.emit(d, self.view.viewport().mapToGlobal(pos))

    def _filter(self) -> None:
        self.proxy.text = self.search.text().strip()
        self.proxy.type_filter = self.type_box.currentData() or ""
        self.proxy.invalidateFilter()
        self._update_count()

    def _update_count(self) -> None:
        n = self.proxy.rowCount()
        total = self.model.rowCount()
        self.count.setText(f"{n} von {total} Geräten" if n != total else f"{total} Geräte")

    def set_devices(self, devices: list[Device], diffs: list[DeviceDiff] | None = None) -> None:
        self.model.set_devices(devices, diffs)
        self._update_count()

    def update_device(self, d: Device) -> None:
        self.model.update_device(d)
        self._update_count()

    def select_ip(self, ip: str) -> None:
        for r in range(self.proxy.rowCount()):
            idx = self.proxy.index(r, 3)
            if idx.data() == ip:
                self.view.selectRow(r)
                self.view.scrollTo(idx)
                return
