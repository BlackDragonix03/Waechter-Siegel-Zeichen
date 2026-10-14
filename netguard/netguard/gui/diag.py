"""Diagnose: erkannte Probleme mit Lösungsvorschlägen und Netzwerk-Übersicht."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QSplitter, QTextBrowser

from ..model import Scan
from ..diagnostics import SEV_ERROR, SEV_WARN, SEV_INFO, SEV_OK
from . import theme

SEV_COLORS = {SEV_ERROR: theme.ERROR, SEV_WARN: theme.WARN, SEV_INFO: theme.ACCENT2, SEV_OK: theme.OK}
SEV_ICONS = {SEV_ERROR: "⛔", SEV_WARN: "⚠️", SEV_INFO: "ℹ️", SEV_OK: "✅"}


class DiagnosticsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(split)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        t = QLabel("Erkannte Probleme und Lösungen")
        t.setObjectName("title")
        ll.addWidget(t)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_host = QWidget()
        self.cards = QVBoxLayout(self.cards_host)
        self.cards.setContentsMargins(0, 0, 8, 0)
        self.cards.setSpacing(8)
        self.cards.addStretch(1)
        self.scroll.setWidget(self.cards_host)
        ll.addWidget(self.scroll, 1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        t2 = QLabel("Netzwerk-Übersicht")
        t2.setObjectName("title")
        rl.addWidget(t2)
        self.info = QTextBrowser()
        self.info.setOpenExternalLinks(True)
        rl.addWidget(self.info, 1)
        split.addWidget(right)
        split.setSizes([600, 400])
        self.set_scan(None)

    def set_scan(self, scan: Scan | None) -> None:
        while self.cards.count() > 1:
            item = self.cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if scan is None:
            self._add_card(SEV_INFO, "Noch kein Scan", "Starte einen Scan, um Probleme zu erkennen.", "")
            self.info.setHtml(f'<p style="color:{theme.TEXT_DIM}">Noch kein Scan.</p>')
            return
        for p in scan.problems:
            self._add_card(p.get("severity", SEV_INFO), p.get("title", ""), p.get("detail", ""), p.get("solution", ""))
        self.info.setHtml(self._info_html(scan))

    def _add_card(self, sev: str, title: str, detail: str, solution: str) -> None:
        card = QFrame()
        card.setObjectName("card")
        color = SEV_COLORS.get(sev, theme.TEXT_DIM)
        card.setStyleSheet(f"QFrame#card {{ border-left: 4px solid {color}; }}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        head = QLabel(f'{SEV_ICONS.get(sev, "")} <b>{_esc(title)}</b> <span style="color:{color}">· {sev}</span>')
        head.setWordWrap(True)
        cl.addWidget(head)
        if detail:
            d = QLabel(_esc(detail))
            d.setWordWrap(True)
            d.setObjectName("dim")
            d.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cl.addWidget(d)
        if solution:
            s = QLabel(f'<span style="color:{theme.ACCENT}">Lösung:</span> {_esc(solution)}')
            s.setWordWrap(True)
            s.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cl.addWidget(s)
        self.cards.insertWidget(self.cards.count() - 1, card)

    def _info_html(self, scan: Scan) -> str:
        rows = []
        for i in scan.interfaces:
            rows.append(f"<tr><td><b>{_esc(i.name)}</b></td><td>{i.ip} / {i.netmask}<br>Gateway: {i.gateway or '–'}<br>MAC: {i.mac or '–'}"
                        f"<br>DNS: {', '.join(i.dns) or '–'}</td></tr>")
        inet = "unbekannt"
        if scan.internet_ok is True:
            inet = f'<span style="color:{theme.OK}">erreichbar</span>'
        elif scan.internet_ok is False:
            inet = f'<span style="color:{theme.ERROR}">nicht erreichbar</span>'
        dns = "unbekannt"
        if scan.dns_ok is True:
            dns = f'<span style="color:{theme.OK}">funktioniert</span>'
        elif scan.dns_ok is False:
            dns = f'<span style="color:{theme.ERROR}">fehlgeschlagen</span>'
        path = " → ".join(scan.internet_path) if scan.internet_path else "–"
        html = f"""
        <style>td {{ padding: 4px 8px; vertical-align: top; }} table {{ border-collapse: collapse; }}</style>
        <h3>Scan</h3>
        <table>
        <tr><td>Zeitpunkt</td><td>{scan.started.replace('T', ' ')} ({scan.duration_s:.0f} s)</td></tr>
        <tr><td>Ziele</td><td>{', '.join(scan.targets)}</td></tr>
        <tr><td>Geräte</td><td>{len(scan.devices)}</td></tr>
        <tr><td>Gateways</td><td>{', '.join(scan.gateways) or '–'}</td></tr>
        <tr><td>Internet</td><td>{inet}{(' · öffentliche IP ' + scan.public_ip) if scan.public_ip else ''}</td></tr>
        <tr><td>DNS</td><td>{dns}</td></tr>
        <tr><td>Weg ins Internet</td><td>{path}</td></tr>
        </table>
        <h3>Schnittstellen</h3>
        <table>{''.join(rows) or '<tr><td>keine</td></tr>'}</table>
        """
        return html


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
