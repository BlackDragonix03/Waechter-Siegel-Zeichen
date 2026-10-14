"""Zugriff der MCP-Tools auf Scans: ohne GUI (headless) oder über das laufende Hauptfenster."""
from __future__ import annotations

import threading
from typing import Any

from .. import storage, diagnostics
from ..model import Scan, Device
from ..net.engine import Scanner, ScanOptions


class Backend:
    """Schnittstelle, die die Tools benutzen."""

    def run_scan(self, opts: ScanOptions, progress=None) -> Scan:
        raise NotImplementedError

    def current_scan(self) -> Scan | None:
        raise NotImplementedError

    def set_current_scan(self, scan: Scan) -> None:
        raise NotImplementedError

    def save_device(self, d: Device) -> None:
        raise NotImplementedError

    def settings(self) -> dict[str, Any]:
        return storage.load_settings()

    def log(self, text: str) -> None:
        pass


class HeadlessBackend(Backend):
    """Ohne Oberfläche (Stdio-Server oder HTTP ohne GUI)."""

    def __init__(self):
        self._scan: Scan | None = None
        self._lock = threading.Lock()
        self.known = storage.load_known()

    def run_scan(self, opts: ScanOptions, progress=None) -> Scan:
        with self._lock:
            scanner = Scanner(opts, progress)
            scan = scanner.run()
            storage.apply_known(scan.devices, self.known)
            for d in scan.devices:
                storage.remember_device(self.known, d)
            storage.save_known(self.known)
            scan.problems = diagnostics.analyze(scan)
            storage.save_scan(scan)
            self._scan = scan
            return scan

    def current_scan(self) -> Scan | None:
        if self._scan is None:
            items = storage.list_scans()
            if items:
                try:
                    self._scan = storage.load_scan(items[0][0])
                    storage.apply_known(self._scan.devices, self.known)
                except Exception:
                    self._scan = None
        return self._scan

    def set_current_scan(self, scan: Scan) -> None:
        self._scan = scan

    def save_device(self, d: Device) -> None:
        storage.remember_device(self.known, d)
        storage.save_known(self.known)
        if self._scan is not None:
            storage.save_scan(self._scan, storage.scan_path(self._scan))
