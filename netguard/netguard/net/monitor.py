"""Live-Überwachung: Geräte regelmäßig anpingen und Router-Zähler abfragen."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import ping as pingmod, arp as arpmod, local
from .router import WanStatus, query_wan, find_igd


@dataclass
class HostState:
    ip: str
    online: bool
    latency_ms: float | None
    checked: float = field(default_factory=time.time)
    last_online: float | None = None
    up_count: int = 0
    total_count: int = 0


@dataclass
class MonitorSample:
    hosts: dict[str, HostState]
    wan: WanStatus | None
    rate_rx_bps: float | None     # aus Zähler-Differenz berechnet (Byte/s)
    rate_tx_bps: float | None
    timestamp: float


class Monitor:
    """Läuft in einem Thread und ruft on_sample(MonitorSample) nach jedem Durchlauf auf."""

    def __init__(self, ips: list[str], interval_s: float = 5.0, router_ip: str = "", query_router: bool = True,
                 on_sample=None, on_error=None):
        self.ips = list(ips)
        self.interval = max(2.0, interval_s)
        self.router_ip = router_ip
        self.query_router = query_router and bool(router_ip)
        self._on_sample = on_sample or (lambda s: None)
        self._on_error = on_error or (lambda e: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.states: dict[str, HostState] = {}
        self._desc_url = ""
        self._last_wan: WanStatus | None = None
        self._ifaces = local.interfaces()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_ips(self, ips: list[str]) -> None:
        self.ips = list(ips)

    def _probe(self, ip: str) -> HostState:
        ok, rtt = pingmod.ping(ip, 800, allow_tcp=True)
        if not ok and local.IS_WINDOWS and local.is_local(ip, self._ifaces):
            ok = bool(arpmod.send_arp(ip))
        st = self.states.get(ip) or HostState(ip, False, None)
        st.online = ok
        st.latency_ms = round(rtt, 1) if (ok and rtt is not None) else None
        st.checked = time.time()
        st.total_count += 1
        if ok:
            st.up_count += 1
            st.last_online = st.checked
        self.states[ip] = st
        return st

    def _run(self) -> None:
        if self.query_router:
            try:
                self._desc_url = find_igd(self.router_ip, 2.0)
            except Exception:
                self._desc_url = ""
        while not self._stop.is_set():
            t0 = time.time()
            ips = list(self.ips)
            try:
                with ThreadPoolExecutor(max_workers=64) as ex:
                    list(ex.map(self._probe, ips))
            except Exception as exc:
                self._on_error(str(exc))
            wan = None
            rate_rx = rate_tx = None
            if self.query_router and not self._stop.is_set():
                try:
                    wan = query_wan(self.router_ip, self._desc_url)
                    if wan.ok and self._last_wan is not None and self._last_wan.ok and wan.total_rx is not None and self._last_wan.total_rx is not None:
                        dt = wan.timestamp - self._last_wan.timestamp
                        if dt > 0:
                            drx = wan.total_rx - self._last_wan.total_rx
                            dtx = (wan.total_tx or 0) - (self._last_wan.total_tx or 0)
                            if drx >= 0:
                                rate_rx = drx / dt
                            if dtx >= 0:
                                rate_tx = dtx / dt
                    if wan.ok:
                        self._last_wan = wan
                except Exception as exc:
                    self._on_error(f"Router: {exc}")
            if wan is not None and wan.ok:
                if rate_rx is None:
                    rate_rx = wan.rate_rx_bps
                if rate_tx is None:
                    rate_tx = wan.rate_tx_bps
            self._on_sample(MonitorSample({ip: self.states[ip] for ip in ips if ip in self.states}, wan, rate_rx, rate_tx, time.time()))
            rest = self.interval - (time.time() - t0)
            while rest > 0 and not self._stop.is_set():
                time.sleep(min(0.25, rest))
                rest -= 0.25
