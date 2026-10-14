"""Reiter „KI / MCP“: MCP-Server ein- und ausschalten, Zugangsdaten, Konfigurationsschnipsel, Protokoll."""
from __future__ import annotations

import json
import secrets
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QCheckBox,
                               QGroupBox, QFormLayout, QPlainTextEdit, QTabWidget, QMessageBox)

from ..mcp.gui_backend import GuiBackend
from ..mcp.http_server import McpHttpServer
from ..mcp.tools import TOOLS
from . import theme


class McpPanel(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.backend = GuiBackend(window)
        self.backend.logged.connect(self._log)
        self.server: McpHttpServer | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        intro = QLabel("Der MCP-Server (Model Context Protocol) macht NetGuard für KI-Werkzeuge wie Claude Desktop, Claude Code oder "
                       "andere MCP-Clients nutzbar: Die KI kann scannen, Geräte abfragen, Probleme analysieren, pingen, den Router abfragen. "
                       "Scans, die die KI anstößt, laufen sichtbar hier in der Oberfläche.")
        intro.setWordWrap(True)
        intro.setObjectName("dim")
        lay.addWidget(intro)

        top = QHBoxLayout()
        lay.addLayout(top)
        box = QGroupBox("HTTP-Server in dieser App")
        f = QFormLayout(box)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(8765)
        f.addRow("Port:", self.port)
        tok_row = QHBoxLayout()
        self.token = QLineEdit()
        self.token.setPlaceholderText("leer = ohne Token (nur lokal sinnvoll)")
        tok_row.addWidget(self.token, 1)
        b_gen = QPushButton("erzeugen")
        b_gen.clicked.connect(lambda: self.token.setText(secrets.token_urlsafe(24)))
        tok_row.addWidget(b_gen)
        f.addRow("Token:", tok_row)
        self.lan = QCheckBox("auch aus dem LAN erreichbar (0.0.0.0) – nur mit Token")
        f.addRow("", self.lan)
        self.autostart = QCheckBox("beim Programmstart automatisch einschalten")
        f.addRow("", self.autostart)
        row = QHBoxLayout()
        self.btn_toggle = QPushButton("▶ MCP-Server einschalten")
        self.btn_toggle.setObjectName("primary")
        self.btn_toggle.clicked.connect(self.toggle)
        row.addWidget(self.btn_toggle)
        self.status = QLabel("aus")
        self.status.setObjectName("dim")
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.status, 1)
        f.addRow("", row)
        top.addWidget(box, 1)

        box2 = QGroupBox(f"Verfügbare Tools ({len(TOOLS)})")
        l2 = QVBoxLayout(box2)
        tools = QLabel(", ".join(t.name for t in TOOLS))
        tools.setWordWrap(True)
        tools.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        l2.addWidget(tools)
        hint = QLabel("Stdio-Variante ohne laufende Oberfläche: <b>NetGuard.exe --mcp</b> (bzw. <code>python netguard.py --mcp</code>). "
                      "Claude Desktop startet den Server so selbst; Scans laufen dann unsichtbar im Hintergrund und landen trotzdem im Verlauf.")
        hint.setWordWrap(True)
        hint.setObjectName("dim")
        l2.addWidget(hint)
        l2.addStretch(1)
        top.addWidget(box2, 1)

        self.snippets = QTabWidget()
        lay.addWidget(self.snippets)
        self.snip_code = self._snippet_tab("Claude Code")
        self.snip_desktop = self._snippet_tab("Claude Desktop (claude_desktop_config.json)")
        self.snip_http = self._snippet_tab("Andere MCP-Clients (HTTP)")
        self._update_snippets()
        for w in (self.port, self.token, self.lan):
            (w.valueChanged if isinstance(w, QSpinBox) else w.textChanged if isinstance(w, QLineEdit) else w.toggled).connect(lambda *_: self._update_snippets())

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(f"font-family: Consolas, 'Cascadia Mono', monospace; font-size: 9.5pt; background: {theme.BG2};")
        lay.addWidget(self.log, 1)

    def _snippet_tab(self, title: str) -> QPlainTextEdit:
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(6, 6, 6, 6)
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setMaximumHeight(130)
        edit.setStyleSheet(f"font-family: Consolas, 'Cascadia Mono', monospace; font-size: 9.5pt; background: {theme.BG2};")
        hl.addWidget(edit)
        b = QPushButton("In die Zwischenablage kopieren")
        b.clicked.connect(lambda: QGuiApplication.clipboard().setText(edit.toPlainText()))
        hl.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        self.snippets.addTab(host, title)
        return edit

    def _exe_command(self) -> tuple[str, list[str]]:
        if getattr(sys, "frozen", False):
            exe = Path(sys.executable).resolve()
            console = exe.parent / "NetGuard-MCP.exe"
            return str(console if console.exists() else exe), ["--mcp"]
        script = str((Path(__file__).resolve().parent.parent.parent / "netguard.py"))
        return str(Path(sys.executable).resolve()), [script, "--mcp"]

    def _update_snippets(self) -> None:
        url = f"http://127.0.0.1:{self.port.value()}/mcp"
        tok = self.token.text().strip()
        hdr = f' --header "Authorization: Bearer {tok}"' if tok else ""
        self.snip_code.setPlainText(
            f"# Im Terminal (Server hier eingeschaltet lassen):\n"
            f"claude mcp add --transport http netguard {url}{hdr}\n\n"
            f"# Oder ohne laufende Oberfläche (Stdio):\n"
            f"claude mcp add netguard -- \"{self._exe_command()[0]}\" {' '.join(self._exe_command()[1])}")
        cmd, args = self._exe_command()
        cfg = {"mcpServers": {"netguard": {"command": cmd, "args": args}}}
        self.snip_desktop.setPlainText(
            "Claude Desktop → Einstellungen → Entwickler → Konfiguration bearbeiten, dann einfügen (Claude Desktop startet NetGuard selbst):\n"
            + json.dumps(cfg, indent=2, ensure_ascii=False))
        headers = {"Authorization": f"Bearer {tok}"} if tok else {}
        self.snip_http.setPlainText(
            f"Transport: Streamable HTTP (JSON-RPC per POST)\nURL: {url}\n"
            + (f"Header: Authorization: Bearer {tok}\n" if tok else "Kein Token gesetzt.\n")
            + "Info-Seite: " + url.replace("/mcp", "/") + "\n"
            + "Beispiel-Konfiguration: " + json.dumps({"mcpServers": {"netguard": {"type": "http", "url": url, "headers": headers}}}, ensure_ascii=False))

    # ------------------------------------------------------------------
    def toggle(self) -> None:
        if self.server is not None and self.server.running:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        tok = self.token.text().strip()
        if self.lan.isChecked() and not tok:
            QMessageBox.warning(self, "Token nötig", "Für den Zugriff aus dem LAN muss ein Token gesetzt sein.")
            return
        host = "0.0.0.0" if self.lan.isChecked() else "127.0.0.1"
        self.server = McpHttpServer(self.backend, self.port.value(), host, tok, self.backend.log)
        try:
            self.server.start()
        except OSError as exc:
            self.server = None
            self.status.setText(f'<span style="color:{theme.ERROR}">Start fehlgeschlagen: {exc}</span>')
            self._log(f"Start fehlgeschlagen: {exc}")
            return
        self.btn_toggle.setText("■ MCP-Server ausschalten")
        self.btn_toggle.setObjectName("danger")
        self.btn_toggle.setStyle(self.btn_toggle.style())
        self.status.setText(f'<span style="color:{theme.OK}">läuft</span> · {self.server.url}' + (" · Token nötig" if tok else " · ohne Token"))
        for w in (self.port, self.lan):
            w.setEnabled(False)
        self.window.statusBar().showMessage(f"MCP-Server läuft: {self.server.url}")

    def stop(self) -> None:
        if self.server is not None:
            self.server.stop()
            self.server = None
        self.btn_toggle.setText("▶ MCP-Server einschalten")
        self.btn_toggle.setObjectName("primary")
        self.btn_toggle.setStyle(self.btn_toggle.style())
        self.status.setText("aus")
        for w in (self.port, self.lan):
            w.setEnabled(True)

    @property
    def running(self) -> bool:
        return self.server is not None and self.server.running

    def _log(self, text: str) -> None:
        self.log.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")

    # ---- Einstellungen --------------------------------------------------------
    def apply_settings(self, s: dict) -> None:
        self.port.setValue(int(s.get("mcp_port", 8765) or 8765))
        self.token.setText(str(s.get("mcp_token", "") or ""))
        self.lan.setChecked(bool(s.get("mcp_lan", False)))
        self.autostart.setChecked(bool(s.get("mcp_autostart", False)))
        self._update_snippets()
        if self.autostart.isChecked():
            self.start()

    def collect_settings(self) -> dict:
        return {"mcp_port": self.port.value(), "mcp_token": self.token.text().strip(), "mcp_lan": self.lan.isChecked(),
                "mcp_autostart": self.autostart.isChecked()}
