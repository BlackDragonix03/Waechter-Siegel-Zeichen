"""Werkzeuge: Ping, Pfad (Traceroute), Port-Check, DNS."""
from __future__ import annotations

import socket
import time

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QPlainTextEdit, QLabel, QComboBox)

from ..net import ping as pingmod, trace as tracemod, ports as portsmod, names as namesmod
from .worker import FuncWorker
from . import theme


class ToolsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: FuncWorker | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Ziel:"))
        self.target = QLineEdit()
        self.target.setPlaceholderText("IP-Adresse oder Name, z.B. 192.168.178.1 oder fritz.box")
        row.addWidget(self.target, 1)
        self.tool = QComboBox()
        self.tool.addItem("Ping (dauerhaft)", "ping")
        self.tool.addItem("Pfad / Traceroute", "trace")
        self.tool.addItem("Port-Check (alle bekannten Ports)", "ports")
        self.tool.addItem("DNS / Namen", "dns")
        row.addWidget(self.tool)
        self.btn_run = QPushButton("Start")
        self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self.run)
        row.addWidget(self.btn_run)
        self.btn_stop = QPushButton("Stopp")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop)
        row.addWidget(self.btn_stop)
        self.btn_clear = QPushButton("Leeren")
        self.btn_clear.clicked.connect(lambda: self.out.clear())
        row.addWidget(self.btn_clear)
        lay.addLayout(row)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setStyleSheet(f"font-family: Consolas, 'Cascadia Mono', monospace; font-size: 10pt; background: {theme.BG2};")
        lay.addWidget(self.out, 1)
        self.target.returnPressed.connect(self.run)

    def start(self, tool: str, ip: str) -> None:
        self.target.setText(ip)
        idx = self.tool.findData(tool)
        if idx >= 0:
            self.tool.setCurrentIndex(idx)
        self.run()

    def run(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        target = self.target.text().strip()
        if not target:
            return
        tool = self.tool.currentData()
        fn = {"ping": self._ping, "trace": self._trace, "ports": self._ports, "dns": self._dns}[tool]
        self.out.appendPlainText(f"\n=== {self.tool.currentText()} → {target}  ({time.strftime('%H:%M:%S')}) ===")
        self.worker = FuncWorker(lambda emit, stopped: fn(target, emit, stopped))
        self.worker.line.connect(self.out.appendPlainText)
        self.worker.done.connect(self._done)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.worker.start()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()

    def _done(self) -> None:
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

    # ------------------------------------------------------------------
    @staticmethod
    def _resolve(target: str, emit) -> str:
        try:
            ip = socket.gethostbyname(target)
        except OSError:
            emit(f"Name {target} konnte nicht aufgelöst werden.")
            return ""
        if ip != target:
            emit(f"{target} → {ip}")
        return ip

    def _ping(self, target: str, emit, stopped) -> None:
        ip = self._resolve(target, emit)
        if not ip:
            return
        sent = ok = 0
        rtts: list[float] = []
        while not stopped():
            sent += 1
            alive, rtt = pingmod.ping(ip, 1000, allow_tcp=False)
            if alive:
                ok += 1
                rtts.append(rtt or 0.0)
                emit(f"Antwort von {ip}: {rtt:.1f} ms" if rtt is not None else f"Antwort von {ip}")
            else:
                emit(f"Keine Antwort von {ip} (Zeitüberschreitung)")
            for _ in range(10):
                if stopped():
                    break
                time.sleep(0.1)
        if sent:
            loss = 100 * (sent - ok) / sent
            stats = f"{sent} gesendet, {ok} empfangen, {loss:.0f}% Verlust"
            if rtts:
                stats += f" · min {min(rtts):.1f} ms, Ø {sum(rtts) / len(rtts):.1f} ms, max {max(rtts):.1f} ms"
            emit(stats)

    def _trace(self, target: str, emit, stopped) -> None:
        ip = self._resolve(target, emit)
        if not ip:
            return
        for hop, addr, rtt in tracemod.traceroute(ip, 30, 1500, stopped):
            if not addr:
                emit(f"{hop:2d}  *  keine Antwort")
                continue
            name = namesmod.reverse_dns(addr, 0.8)
            line = f"{hop:2d}  {addr:<16}"
            if rtt is not None:
                line += f" {rtt:7.1f} ms"
            if name:
                line += f"  {name}"
            emit(line)
        emit("Pfad beendet.")

    def _ports(self, target: str, emit, stopped) -> None:
        ip = self._resolve(target, emit)
        if not ip:
            return
        emit(f"Prüfe {len(portsmod.FULL_PORTS)} Ports …")
        found = portsmod.scan_ports(ip, portsmod.FULL_PORTS, timeout=0.8, workers=48)
        if not found:
            emit("Keine offenen Ports gefunden.")
            return
        for p in found:
            extra = ""
            if p in (80, 443, 8080, 8443, 5000, 5001, 8000, 8123):
                t, s = portsmod.http_title(ip, p)
                extra = " · ".join(x for x in (t, s) if x)
            elif p == 22:
                extra = portsmod.banner(ip, p)
            emit(f"{p:>6}  {portsmod.service_name(p):<28} {extra}")
        emit(f"{len(found)} offene Ports.")

    def _dns(self, target: str, emit, stopped) -> None:
        try:
            infos = socket.getaddrinfo(target, None)
            ips = sorted({i[4][0] for i in infos})
            emit("Adressen: " + ", ".join(ips))
        except OSError as exc:
            emit(f"Auflösung fehlgeschlagen: {exc}")
            ips = []
        for ip in ips[:3]:
            if ":" in ip:
                continue
            emit(f"Reverse-DNS {ip}: {namesmod.reverse_dns(ip) or '–'}")
            nb, grp = namesmod.netbios_name(ip, 1.0)
            emit(f"NetBIOS {ip}: {nb or '–'}" + (f" (Arbeitsgruppe {grp})" if grp else ""))
            emit(f"mDNS {ip}: {namesmod.mdns_name(ip, 1.0) or '–'}")
