"""Scan in einem eigenen Thread, damit die Oberfläche flüssig bleibt."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from ..net.engine import Scanner, ScanOptions, ScanCancelled


class ScanWorker(QThread):
    progress = Signal(str, int, int, str)
    device_found = Signal(object)
    finished_scan = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, options: ScanOptions, parent=None):
        super().__init__(parent)
        self._scanner = Scanner(options, self._on_progress, self._on_device)

    def _on_progress(self, phase: str, done: int, total: int, msg: str) -> None:
        self.progress.emit(phase, done, total, msg)

    def _on_device(self, device) -> None:
        self.device_found.emit(device)

    def cancel(self) -> None:
        self._scanner.cancel()

    def run(self) -> None:
        try:
            scan = self._scanner.run()
        except ScanCancelled:
            self.cancelled.emit()
            return
        except Exception:
            self.failed.emit(traceback.format_exc())
            return
        self.finished_scan.emit(scan)


class FuncWorker(QThread):
    """Führt eine Funktion im Hintergrund aus und liefert Textzeilen (für Werkzeuge)."""
    line = Signal(str)
    done = Signal()

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    @property
    def stopped(self) -> bool:
        return self._stop

    def run(self) -> None:
        try:
            self._fn(self.line.emit, lambda: self._stop)
        except Exception as exc:  # pragma: no cover
            self.line.emit(f"Fehler: {exc}")
        self.done.emit()
