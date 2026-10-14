"""Einstellungen: Sichtbarkeit des KI-Reiters, lokale KI, Datenordner."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QLabel, QGroupBox, QFormLayout

from .. import storage


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        box = QGroupBox("KI")
        f = QFormLayout(box)
        self.show_ai_tab = QCheckBox("Reiter „KI / MCP“ anzeigen")
        self.show_ai_tab.setChecked(bool(settings.get("show_ai_tab", True)))
        f.addRow(self.show_ai_tab)
        self.local_ai = QCheckBox("Lokale KI (Ollama) einschalten")
        self.local_ai.setChecked(bool(settings.get("local_ai", False)))
        self.local_ai.setToolTip("Zeigt im KI-Reiter den Bereich „Lokale KI“ mit Modell-Download und Chat. Ausgeschaltet ist davon nichts sichtbar.")
        f.addRow(self.local_ai)
        hint = QLabel("Die lokale KI läuft über Ollama (separat installiert, kostenlos). Modelle von 0,5B bis 4B lassen sich im Reiter laden.")
        hint.setWordWrap(True)
        hint.setObjectName("dim")
        f.addRow(hint)
        lay.addWidget(box)
        box2 = QGroupBox("Daten")
        f2 = QFormLayout(box2)
        p = QLabel(str(storage.data_dir()))
        p.setWordWrap(True)
        f2.addRow("Datenordner:", p)
        lay.addWidget(box2)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def values(self) -> dict:
        return {"show_ai_tab": self.show_ai_tab.isChecked(), "local_ai": self.local_ai.isChecked()}
