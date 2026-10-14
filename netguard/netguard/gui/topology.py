"""Zoombare Netzwerk-Topologie als Baum um den Router."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QImage, QFontMetricsF)
from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsObject, QGraphicsItem, QGraphicsLineItem,
                               QStyleOptionGraphicsItem, QWidget, QLabel, QVBoxLayout, QFrame)

from ..model import Scan, Device, DeviceDiff, STATUS_NEW, STATUS_MISSING, STATUS_CHANGED
from ..classify import type_icon, type_color, type_label
from . import theme

NODE_W = 168.0
NODE_H = 52.0

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


# ---------------------------------------------------------------------------
# Radiales Layout um die Wurzel (ungerichtet)
# ---------------------------------------------------------------------------
def radial_layout(nodes: dict[str, NodeData], edges: list[tuple[str, str]], root: str) -> dict[str, QPointF]:
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        if a in adj and b in adj:
            adj[a].append(b)
            adj[b].append(a)
    # Baum per BFS von der Wurzel
    children: dict[str, list[str]] = {n: [] for n in nodes}
    depth: dict[str, int] = {root: 0}
    order = [root]
    i = 0
    while i < len(order):
        n = order[i]
        i += 1
        for m in adj[n]:
            if m not in depth:
                depth[m] = depth[n] + 1
                children[n].append(m)
                order.append(m)
    for n in nodes:  # nicht verbundene Knoten
        if n not in depth:
            depth[n] = 1
            children[root].append(n)

    # Kinder sortieren: Internet-Kette zuerst, dann nach Typ und IP
    type_order = {"internet": 0, "router": 1, "switch": 2, "self": 3, "server": 4, "nas": 5, "pc": 6, "vm": 7,
                  "printer": 8, "camera": 9, "tv": 10, "console": 11, "speaker": 12, "phone": 13, "iot": 14, "unknown": 15}

    def sort_key(nid: str):
        nd = nodes[nid]
        ipn = 0
        if nd.device is not None:
            ipn = nd.device.ip_int()
        return (type_order.get(nd.kind if nd.kind == "internet" else nd.dtype, 20), ipn)

    for n in children:
        children[n].sort(key=sort_key)

    leaves: dict[str, int] = {}

    def count(n: str) -> int:
        if not children[n]:
            leaves[n] = 1
        else:
            leaves[n] = sum(count(c) for c in children[n])
        return leaves[n]

    count(root)

    per_depth: dict[int, int] = {}
    for n, d in depth.items():
        per_depth[d] = per_depth.get(d, 0) + 1
    # Volle Ebenen werden auf mehrere konzentrische Ringe verteilt
    rings: dict[int, int] = {}
    radius: dict[int, float] = {0: 0.0}
    max_depth = max(depth.values()) if depth else 0
    ring_gap = NODE_W + 30
    for d in range(1, max_depth + 1):
        n = per_depth.get(d, 0)
        k = 1 if n <= 14 else 2 if n <= 50 else 3 if n <= 120 else 4
        rings[d] = k
        need = (n / k) * (NODE_W + 26) / (2 * math.pi)
        inner = max(radius[d - 1] + 230.0 + (rings.get(d - 1, 1) - 1) * ring_gap, need, 230.0)
        radius[d] = inner

    pos: dict[str, QPointF] = {root: QPointF(0, 0)}

    def place(n: str, a0: float, a1: float) -> None:
        kids = children[n]
        if not kids:
            return
        total = sum(leaves[c] for c in kids)
        # Internet-Zweig bekommt einen festen Sektor oben, wenn wir an der Wurzel sind
        a = a0
        span = a1 - a0
        reserved: dict[str, tuple[float, float]] = {}
        if n == root:
            inet = [c for c in kids if "internet" in _subtree_kinds(c, children, nodes)]
            if inet and len(kids) > 1:
                c = inet[0]
                reserved[c] = (-math.pi / 2 - 0.22, -math.pi / 2 + 0.22)
                kids = [k for k in kids if k != c]
                total = sum(leaves[k] for k in kids) or 1
                a = -math.pi / 2 + 0.22
                span = 2 * math.pi - 0.44
        for idx, c in enumerate(kids):
            frac = leaves[c] / total if total else 1.0
            ca0 = a
            ca1 = a + span * frac
            mid = (ca0 + ca1) / 2
            r = radius[depth[c]] + (idx % rings.get(depth[c], 1)) * ring_gap
            pos[c] = QPointF(r * math.cos(mid), r * math.sin(mid))
            place(c, ca0, ca1)
            a = ca1
        for c, (ca0, ca1) in reserved.items():
            mid = (ca0 + ca1) / 2
            r = radius[depth[c]]
            pos[c] = QPointF(r * math.cos(mid), r * math.sin(mid))
            place(c, ca0, ca1)

    place(root, -math.pi / 2, 3 * math.pi / 2)
    return pos


def _subtree_kinds(n: str, children: dict[str, list[str]], nodes: dict[str, NodeData]) -> set[str]:
    out = {nodes[n].kind}
    stack = list(children[n])
    while stack:
        x = stack.pop()
        out.add(nodes[x].kind)
        stack.extend(children[x])
    return out


# ---------------------------------------------------------------------------
# Grafik-Elemente
# ---------------------------------------------------------------------------
class EdgeItem(QGraphicsLineItem):
    def __init__(self, a: "NodeItem", b: "NodeItem"):
        super().__init__()
        self.a = a
        self.b = b
        self.setZValue(-1)
        color = QColor("#3b4b5c")
        pen = QPen(color, 2.0)
        if a.data.status == STATUS_MISSING or b.data.status == STATUS_MISSING:
            pen = QPen(QColor(STATUS_COLORS[STATUS_MISSING]), 1.5, Qt.PenStyle.DashLine)
        elif a.data.status == STATUS_NEW or b.data.status == STATUS_NEW:
            pen = QPen(QColor(STATUS_COLORS[STATUS_NEW]), 2.0)
        self.setPen(pen)
        self.update_pos()

    def update_pos(self) -> None:
        pa = self.a.pos() + QPointF(NODE_W / 2, NODE_H / 2)
        pb = self.b.pos() + QPointF(NODE_W / 2, NODE_H / 2)
        self.setLine(pa.x(), pa.y(), pb.x(), pb.y())


class NodeItem(QGraphicsObject):
    clicked = Signal(object)
    double_clicked = Signal(object)
    context = Signal(object, object)

    def __init__(self, data: NodeData):
        super().__init__()
        self.data = data
        self.edges: list[EdgeItem] = []
        self._hover = False
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._tooltip())

    # --- Geometrie -------------------------------------------------------
    def boundingRect(self) -> QRectF:
        return QRectF(-6, -6, NODE_W + 12, NODE_H + 12)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRoundedRect(QRectF(0, 0, NODE_W, NODE_H), 10, 10)
        return p

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for e in self.edges:
                e.update_pos()
        return super().itemChange(change, value)

    # --- Darstellung -----------------------------------------------------
    def _tooltip(self) -> str:
        d = self.data.device
        if d is None:
            if self.data.kind == "internet":
                return "Internet\n" + (self.data.subtitle or "")
            return self.data.title
        lines = [f"<b>{_esc(d.display_name)}</b>", f"IP: {d.ip}"]
        if d.mac:
            lines.append(f"MAC: {d.mac}" + (f" ({_esc(d.vendor)})" if d.vendor else ""))
        lines.append(f"Typ: {type_label(d.device_type)}")
        for label, val in (("DNS", d.hostname), ("NetBIOS", d.netbios_name), ("mDNS", d.mdns_name), ("UPnP", d.ssdp_name), ("Modell", d.ssdp_model)):
            if val:
                lines.append(f"{label}: {_esc(val)}")
        if d.open_ports:
            lines.append("Ports: " + ", ".join(map(str, d.open_ports[:12])) + (" …" if len(d.open_ports) > 12 else ""))
        if d.latency_ms is not None:
            lines.append(f"Antwortzeit: {d.latency_ms:.1f} ms")
        if d.admin_url:
            lines.append(f"Zugang: {_esc(d.admin_url)}")
        if self.data.status:
            lines.append(f"<b>Status: {self.data.status}</b>")
            for c in self.data.changes:
                lines.append("· " + _esc(c))
        return "<br>".join(lines)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, NODE_W, NODE_H)
        color = QColor(type_color(self.data.dtype))
        if self.data.kind == "internet":
            color = QColor("#4c8dff")
        bg = QColor(theme.BG2)
        border = QColor(theme.BORDER)
        pen_w = 1.5
        style = Qt.PenStyle.SolidLine
        if self.data.status in STATUS_COLORS:
            border = QColor(STATUS_COLORS[self.data.status])
            pen_w = 2.5
            if self.data.status == STATUS_MISSING:
                style = Qt.PenStyle.DashLine
                bg = QColor("#1a1416")
        elif self.data.device is not None and (self.data.device.is_gateway or self.data.device.is_self):
            border = color
            pen_w = 2.0
        if self.isSelected():
            border = QColor(theme.ACCENT2)
            pen_w = 3.0
        elif self._hover:
            bg = QColor(theme.BG3)
        # Schatten
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawRoundedRect(rect.translated(2, 3), 10, 10)
        painter.setBrush(bg)
        painter.setPen(QPen(border, pen_w, style))
        painter.drawRoundedRect(rect, 10, 10)
        # Farbbalken links
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 7, NODE_H), 10, 10)
        path.addRect(QRectF(4, 0, 3, NODE_H))
        painter.drawPath(path)
        # Symbol
        icon = "🌐" if self.data.kind == "internet" else ("🔀" if self.data.kind == "subnet" else type_icon(self.data.dtype))
        f = QFont()
        f.setPointSizeF(15)
        painter.setFont(f)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(QRectF(12, 0, 30, NODE_H), Qt.AlignmentFlag.AlignCenter, icon)
        # Titel + Untertitel
        f = QFont()
        f.setPointSizeF(9.5)
        f.setBold(True)
        painter.setFont(f)
        fm = QFontMetricsF(f)
        title = fm.elidedText(self.data.title, Qt.TextElideMode.ElideRight, NODE_W - 56)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(QRectF(46, 6, NODE_W - 52, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)
        f2 = QFont()
        f2.setPointSizeF(8.5)
        painter.setFont(f2)
        painter.setPen(QColor(theme.TEXT_DIM))
        sub = self.data.subtitle
        if self.data.device is not None and self.data.device.latency_ms is not None and self.data.status != STATUS_MISSING:
            sub = f"{sub}  ·  {self.data.device.latency_ms:.0f} ms"
        painter.drawText(QRectF(46, 26, NODE_W - 52, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         QFontMetricsF(f2).elidedText(sub, Qt.TextElideMode.ElideRight, NODE_W - 52))
        # Status-Marke
        if self.data.status in STATUS_COLORS:
            f3 = QFont()
            f3.setPointSizeF(7.5)
            f3.setBold(True)
            painter.setFont(f3)
            text = self.data.status.upper()
            w = QFontMetricsF(f3).horizontalAdvance(text) + 12
            badge = QRectF(NODE_W - w - 4, -8, w, 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(STATUS_COLORS[self.data.status]))
            painter.drawRoundedRect(badge, 8, 8)
            painter.setPen(QColor("#06231a") if self.data.status == STATUS_NEW else QColor("#1a0a0a"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
        elif self.data.device is not None and self.data.device.trusted:
            f3 = QFont()
            f3.setPointSizeF(8)
            painter.setFont(f3)
            painter.setPen(QColor(theme.ACCENT))
            painter.drawText(QRectF(NODE_W - 22, 2, 18, 14), Qt.AlignmentFlag.AlignCenter, "✔")

    # --- Maus -------------------------------------------------------------
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.data)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.double_clicked.emit(self.data)

    def contextMenuEvent(self, event):
        self.context.emit(self.data, event.screenPos())
        event.accept()


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Ansicht
# ---------------------------------------------------------------------------
class TopologyView(QGraphicsView):
    node_selected = Signal(object)        # Device oder None
    node_activated = Signal(object)       # Doppelklick
    node_context = Signal(object, object)  # Device, QPoint

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setBackgroundBrush(QBrush(QColor(theme.BG)))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._items: dict[str, NodeItem] = {}
        self._zoom = 1.0
        self._legend = _Legend(self)
        self._empty = QLabel("Noch keine Topologie.\nStarte einen Scan oder lade einen gespeicherten Scan.", self)
        self._empty.setObjectName("dim")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 13pt; background: transparent;")

    # --- Aufbau -------------------------------------------------------------
    def set_scan(self, scan: Scan | None, diffs: list[DeviceDiff] | None = None) -> None:
        self._scene.clear()
        self._items.clear()
        if scan is None or not scan.devices and not scan.interfaces:
            self._empty.show()
            return
        self._empty.hide()
        nodes, edges, root = build_graph(scan, diffs)
        pos = radial_layout(nodes, edges, root)
        for nid, nd in nodes.items():
            it = NodeItem(nd)
            p = pos.get(nid, QPointF(0, 0))
            it.setPos(p.x() - NODE_W / 2, p.y() - NODE_H / 2)
            it.clicked.connect(self._on_clicked)
            it.double_clicked.connect(lambda d: self.node_activated.emit(d.device))
            it.context.connect(lambda d, gp: self.node_context.emit(d.device, gp))
            self._scene.addItem(it)
            self._items[nid] = it
        for a, b in edges:
            if a in self._items and b in self._items:
                e = EdgeItem(self._items[a], self._items[b])
                self._items[a].edges.append(e)
                self._items[b].edges.append(e)
                self._scene.addItem(e)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-300, -300, 300, 300))
        self.fit()

    def _on_clicked(self, nd: NodeData) -> None:
        self.node_selected.emit(nd.device)

    def select_ip(self, ip: str) -> None:
        for nid, it in self._items.items():
            it.setSelected(nid == "dev:" + ip)
            if nid == "dev:" + ip:
                self.centerOn(it)

    def refresh_device(self, device: Device) -> None:
        it = self._items.get("dev:" + device.ip)
        if it is None:
            return
        it.data.device = device
        it.data.dtype = device.device_type
        it.data.title = node_title(device)
        it.setToolTip(it._tooltip())
        it.update()

    # --- Zoom -----------------------------------------------------------------
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = self._zoom * factor
        if 0.05 <= new_zoom <= 8.0:
            self._zoom = new_zoom
            self.scale(factor, factor)
        event.accept()

    def zoom_in(self) -> None:
        self._apply_zoom(1.25)

    def zoom_out(self) -> None:
        self._apply_zoom(1 / 1.25)

    def _apply_zoom(self, factor: float) -> None:
        new_zoom = self._zoom * factor
        if 0.05 <= new_zoom <= 8.0:
            self._zoom = new_zoom
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            self.scale(factor, factor)
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def fit(self) -> None:
        if not self._items:
            return
        self.resetTransform()
        self._zoom = 1.0
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        if self._zoom > 1.6:
            self.resetTransform()
            self.scale(1.6, 1.6)
            self._zoom = 1.6
            self.centerOn(rect.center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._legend.move(12, self.viewport().height() - self._legend.height() - 12)
        self._empty.setGeometry(0, 0, self.viewport().width(), self.viewport().height())

    def export_png(self, path: str) -> bool:
        rect = self._scene.itemsBoundingRect().adjusted(-60, -60, 60, 60)
        scale = 2.0
        img = QImage(int(rect.width() * scale), int(rect.height() * scale), QImage.Format.Format_ARGB32)
        img.fill(QColor(theme.BG))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._scene.render(painter, QRectF(0, 0, img.width(), img.height()), rect)
        painter.end()
        return img.save(path)


class _Legend(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ background: rgba(22,29,38,220); border: 1px solid {theme.BORDER}; border-radius: 8px; }} QLabel {{ background: transparent; color: {theme.TEXT_DIM}; font-size: 8.5pt; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)
        lay.addWidget(QLabel("Mausrad: Zoom · Ziehen: Verschieben · Klick: Details · Doppelklick: Weboberfläche"))
        row = QLabel(f'<span style="color:{STATUS_COLORS[STATUS_NEW]}">■</span> neu &nbsp; '
                     f'<span style="color:{STATUS_COLORS[STATUS_CHANGED]}">■</span> geändert &nbsp; '
                     f'<span style="color:{STATUS_COLORS[STATUS_MISSING]}">■</span> fehlt (im Vergleich) &nbsp; '
                     f'<span style="color:{theme.ACCENT}">✔</span> bekannt')
        lay.addWidget(row)
        self.adjustSize()
