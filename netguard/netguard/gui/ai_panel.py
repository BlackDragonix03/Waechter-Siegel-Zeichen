"""Lokale KI (Ollama): ein-/ausschaltbar, Modelle laden, Chat mit NetGuard-Werkzeugen."""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QGroupBox,
                               QFormLayout, QProgressBar, QTextBrowser, QCheckBox)

from ..ai import ollama
from ..mcp.tools import tool_descriptions, call_tool
from . import theme

SYSTEM_PROMPT = (
    "Du bist der Netzwerk-Assistent von NetGuard. Du hilfst beim Verstehen des Heimnetzes und bei der Fehlersuche. "
    "Antworte auf Deutsch, kurz und konkret. Nutze die Werkzeuge, um echte Daten zu holen, statt zu raten: "
    "get_current_scan für die Übersicht, get_devices/get_device für Geräte, get_problems für Diagnose, "
    "scan_network nur, wenn ein neuer Scan nötig ist (dauert lange). Nenne IPs und Namen genau so, wie die Werkzeuge sie liefern."
)


class _Bridge(QObject):
    line = Signal(str, str)        # art, text
    progress = Signal(str, int, int)
    done = Signal(str)             # Fehlertext oder ""
    models = Signal(object)


class AiPanel(QWidget):
    """Wird nur angezeigt, wenn die lokale KI eingeschaltet ist."""

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.bridge = _Bridge()
        self.bridge.line.connect(self._on_line)
        self.bridge.progress.connect(self._on_progress)
        self.bridge.done.connect(self._on_done)
        self.bridge.models.connect(self._on_models)
        self.messages: list[dict] = []
        self._busy = False
        self._stop = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        lay.addLayout(top)

        box = QGroupBox("Ollama")
        f = QFormLayout(box)
        self.url = QLineEdit(ollama.DEFAULT_URL)
        f.addRow("Adresse:", self.url)
        self.status = QLabel("nicht geprüft")
        self.status.setWordWrap(True)
        self.status.setObjectName("dim")
        f.addRow("Status:", self.status)
        row = QHBoxLayout()
        self.btn_check = QPushButton("Verbindung prüfen")
        self.btn_check.clicked.connect(self.refresh)
        row.addWidget(self.btn_check)
        link = QLabel('<a href="https://ollama.com/download" style="color:%s">Ollama herunterladen</a>' % theme.ACCENT2)
        link.setOpenExternalLinks(True)
        row.addWidget(link)
        f.addRow("", row)
        top.addWidget(box, 1)

        box2 = QGroupBox("Modell")
        f2 = QFormLayout(box2)
        self.model = QComboBox()
        self.model.setEditable(True)
        for name, label, size, hint in ollama.SUGGESTED_MODELS:
            self.model.addItem(f"{label} · {size} · {hint}", name)
        self.model.setCurrentIndex(3)
        f2.addRow("Modell:", self.model)
        self.installed = QLabel("installiert: –")
        self.installed.setWordWrap(True)
        self.installed.setObjectName("dim")
        f2.addRow("", self.installed)
        row2 = QHBoxLayout()
        self.btn_pull = QPushButton("⇩ Modell herunterladen")
        self.btn_pull.clicked.connect(self.pull)
        row2.addWidget(self.btn_pull)
        self.btn_delete = QPushButton("Modell löschen")
        self.btn_delete.clicked.connect(self.delete)
        row2.addWidget(self.btn_delete)
        f2.addRow("", row2)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        f2.addRow("", self.progress)
        top.addWidget(box2, 2)

        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        lay.addWidget(self.chat, 1)
        bottom = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Frage zum Netzwerk, z.B. „Welche Geräte sind neu?“ oder „Warum habe ich kein Internet?“")
        self.input.returnPressed.connect(self.send)
        bottom.addWidget(self.input, 1)
        self.use_tools = QCheckBox("Werkzeuge")
        self.use_tools.setChecked(True)
        self.use_tools.setToolTip("Die KI darf NetGuard-Werkzeuge aufrufen (Scan, Geräte, Diagnose, Ping …)")
        bottom.addWidget(self.use_tools)
        self.btn_send = QPushButton("Senden")
        self.btn_send.setObjectName("primary")
        self.btn_send.clicked.connect(self.send)
        bottom.addWidget(self.btn_send)
        self.btn_stop = QPushButton("Stopp")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        bottom.addWidget(self.btn_stop)
        self.btn_clear = QPushButton("Neu")
        self.btn_clear.setToolTip("Gespräch leeren")
        self.btn_clear.clicked.connect(self.clear)
        bottom.addWidget(self.btn_clear)
        lay.addLayout(bottom)
        self.clear()

    # ------------------------------------------------------------------
    def _model_name(self) -> str:
        data = self.model.currentData()
        text = self.model.currentText().strip()
        if data and self.model.itemText(self.model.currentIndex()) == text:
            return str(data)
        return text.split(" ·")[0].strip()

    def refresh(self) -> None:
        base = self.url.text().strip() or ollama.DEFAULT_URL

        def job():
            ok, info = ollama.available(base)
            models = []
            if ok:
                try:
                    models = ollama.list_models(base)
                except Exception as exc:
                    info += f" (Modelle nicht lesbar: {exc})"
            self.bridge.models.emit((ok, info, models))
        threading.Thread(target=job, daemon=True).start()

    def _on_models(self, payload) -> None:
        ok, info, models = payload
        if ok:
            self.status.setText(f'<span style="color:{theme.OK}">erreichbar</span> · Version {info}')
        else:
            self.status.setText(f'<span style="color:{theme.ERROR}">{info}</span>')
        if models:
            self.installed.setText("installiert: " + ", ".join(f"{m.name} ({ollama.human_size(m.size_bytes)})" for m in models))
            names = {m.name for m in models}
            for i in range(self.model.count()):
                base_name = str(self.model.itemData(i) or "")
                label = self.model.itemText(i).replace(" ✔", "")
                if base_name in names or base_name.replace(":latest", "") in names:
                    label += " ✔"
                self.model.setItemText(i, label)
        else:
            self.installed.setText("installiert: keine Modelle" if ok else "installiert: –")

    def pull(self) -> None:
        if self._busy:
            return
        name = self._model_name()
        if not name:
            return
        base = self.url.text().strip() or ollama.DEFAULT_URL
        self._busy = True
        self._stop = False
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._set_busy(True)
        self._append("system", f"Lade Modell {name} …")

        def job():
            try:
                ok = ollama.pull_model(name, base, lambda s, c, t: self.bridge.progress.emit(s, c, t), lambda: self._stop)
                self.bridge.done.emit("" if ok else "Download abgebrochen.")
            except Exception as exc:
                self.bridge.done.emit(f"Download fehlgeschlagen: {exc}")
        threading.Thread(target=job, daemon=True).start()

    def delete(self) -> None:
        name = self._model_name()
        base = self.url.text().strip() or ollama.DEFAULT_URL
        try:
            ollama.delete_model(name, base)
            self._append("system", f"Modell {name} gelöscht.")
        except Exception as exc:
            self._append("system", f"Löschen fehlgeschlagen: {exc}")
        self.refresh()

    def _on_progress(self, status: str, done: int, total: int) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.progress.setFormat(f"{status} {ollama.human_size(done)} / {ollama.human_size(total)}")
        else:
            self.progress.setRange(0, 0)
            self.progress.setFormat(status)

    def _on_done(self, error: str) -> None:
        self._busy = False
        self._set_busy(False)
        self.progress.setVisible(False)
        if error:
            self._append("system", error)
        else:
            self._append("system", "Fertig.")
        self.refresh()

    def _set_busy(self, busy: bool) -> None:
        for w in (self.btn_pull, self.btn_delete, self.btn_send, self.input):
            w.setEnabled(not busy)
        self.btn_stop.setEnabled(busy)

    def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------------
    def clear(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.chat.clear()
        self._append("system", "Lokale KI bereit. Fragen zum Netzwerk stellen; die KI nutzt bei Bedarf die NetGuard-Werkzeuge.")

    def _append(self, who: str, text: str) -> None:
        esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        color = {"user": theme.ACCENT2, "ai": theme.TEXT, "tool": theme.WARN, "system": theme.TEXT_DIM}.get(who, theme.TEXT)
        label = {"user": "Du", "ai": "KI", "tool": "Werkzeug", "system": "·"}.get(who, who)
        self.chat.append(f'<p style="margin:4px 0"><span style="color:{color}"><b>{label}</b></span> &nbsp;<span style="color:{color if who != "ai" else theme.TEXT}">{esc}</span></p>')

    def send(self) -> None:
        if self._busy:
            return
        text = self.input.text().strip()
        if not text:
            return
        model = self._model_name()
        base = self.url.text().strip() or ollama.DEFAULT_URL
        self.input.clear()
        self._append("user", text)
        self.messages.append({"role": "user", "content": text})
        self._busy = True
        self._stop = False
        self._set_busy(True)
        tools = ollama.tools_for_ollama(tool_descriptions()) if self.use_tools.isChecked() else None
        backend = self.backend

        def job():
            t0 = time.time()
            try:
                ollama.chat(self.messages, model, tools, lambda n, a: call_tool(backend, n, a), base,
                            on_event=lambda a, t: self.bridge.line.emit(a, t), stop=lambda: self._stop)
                self.bridge.done.emit("")
            except Exception as exc:
                self.bridge.done.emit(f"KI-Fehler: {exc}")
            self.bridge.line.emit("system", f"({time.time() - t0:.0f} s)")
        threading.Thread(target=job, daemon=True).start()

    def _on_line(self, kind: str, text: str) -> None:
        if kind == "tool":
            self._append("tool", "→ " + text)
        elif kind == "result":
            self._append("tool", "← " + text)
        elif kind == "text":
            if text:
                self._append("ai", text)
        else:
            self._append("system", text)

    # ---- Einstellungen --------------------------------------------------------
    def apply_settings(self, s: dict) -> None:
        self.url.setText(str(s.get("ollama_url", ollama.DEFAULT_URL) or ollama.DEFAULT_URL))
        if s.get("ollama_model"):
            idx = self.model.findData(s["ollama_model"])
            if idx >= 0:
                self.model.setCurrentIndex(idx)
            else:
                self.model.setEditText(str(s["ollama_model"]))

    def collect_settings(self) -> dict:
        return {"ollama_url": self.url.text().strip(), "ollama_model": self._model_name()}
