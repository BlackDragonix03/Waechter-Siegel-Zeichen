"""Backend, das die Tools über das laufende Hauptfenster ausführt (Scans sichtbar in der GUI)."""
from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from .. import storage
from ..model import Scan, Device
from ..net.engine import ScanOptions
from .backend import Backend


class _Call:
    def __init__(self, fn: Callable[[], Any]):
        self.fn = fn
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


class GuiBackend(QObject, Backend):
    _call = Signal(object)
    logged = Signal(str)

    def __init__(self, window):
        QObject.__init__(self)
        self.window = window
        self._call.connect(self._run_call)
        self._scan_lock = threading.Lock()

    # ---- Aufrufe im GUI-Thread ausführen ----------------------------------------
    def _run_call(self, call: _Call) -> None:
        try:
            call.result = call.fn()
        except BaseException as exc:  # noqa: BLE001
            call.error = exc
        call.done.set()

    def invoke(self, fn: Callable[[], Any], timeout: float = 60.0) -> Any:
        if threading.current_thread() is threading.main_thread():
            return fn()
        call = _Call(fn)
        self._call.emit(call)
        if not call.done.wait(timeout):
            raise TimeoutError("Die Oberfläche hat nicht rechtzeitig geantwortet.")
        if call.error is not None:
            raise call.error
        return call.result

    # ---- Backend ---------------------------------------------------------------
    def run_scan(self, opts: ScanOptions, progress=None) -> Scan:
        if not self._scan_lock.acquire(timeout=1.0):
            raise ValueError("Ein Scan über MCP läuft bereits. Bitte warten.")
        try:
            finished = threading.Event()
            outcome: dict[str, Any] = {}

            def start():
                w = self.window
                if w.worker is not None and w.worker.isRunning():
                    raise ValueError("In der Oberfläche läuft bereits ein Scan. Bitte warten, bis er fertig ist.")
                worker = w.start_scan(opts=opts)
                if worker is None:
                    raise ValueError("Scan konnte nicht gestartet werden (keine Ziele?).")
                worker.finished_scan.connect(lambda s: (outcome.__setitem__("scan", s), finished.set()))
                worker.cancelled.connect(lambda: (outcome.__setitem__("error", "Scan wurde abgebrochen."), finished.set()))
                worker.failed.connect(lambda t: (outcome.__setitem__("error", t[-500:]), finished.set()))

            self.invoke(start)
            if not finished.wait(timeout=3600):
                raise ValueError("Scan dauert zu lange (über eine Stunde).")
            if "error" in outcome:
                raise ValueError(outcome["error"])
            # Das Hauptfenster hat den Scan bereits verarbeitet (bekannte Geräte, Vergleich, Speichern)
            return self.invoke(lambda: self.window.scan) or outcome["scan"]
        finally:
            self._scan_lock.release()

    def current_scan(self) -> Scan | None:
        return self.window.scan

    def set_current_scan(self, scan: Scan) -> None:
        self.invoke(lambda: self.window.show_scan_object(scan))

    def save_device(self, d: Device) -> None:
        self.invoke(lambda: self.window._device_saved(d))

    def settings(self) -> dict[str, Any]:
        def read():
            s = dict(storage.load_settings())
            live = self.window.live
            s["router_ip"] = live.router_ip.text().strip() or s.get("router_ip", "")
            s["tr064_user"] = live.tr_user.text().strip() or s.get("tr064_user", "")
            s["tr064_password"] = live.tr_pass.text() or s.get("tr064_password", "")
            s["snmp_community"] = live.snmp_comm.text().strip() or s.get("snmp_community", "public")
            return s
        try:
            return self.invoke(read, timeout=5.0)
        except Exception:
            return storage.load_settings()

    def log(self, text: str) -> None:
        self.logged.emit(text)
