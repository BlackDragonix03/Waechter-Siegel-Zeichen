"""Traceroute über ICMP mit steigender TTL."""
from __future__ import annotations

from .ping import ping_ttl


def traceroute(ip: str, max_hops: int = 20, timeout_ms: int = 800, stop=None) -> list[tuple[int, str, float | None]]:
    """Liste von (Hop-Nr, Adresse oder "", Laufzeit). Endet, wenn das Ziel antwortet."""
    hops: list[tuple[int, str, float | None]] = []
    misses = 0
    for ttl in range(1, max_hops + 1):
        if stop is not None and stop():
            break
        reached, addr, rtt = ping_ttl(ip, ttl, timeout_ms)
        if rtt is not None and rtt < 0:
            # "Ziel unerreichbar": Pfad endet hier
            hops.append((ttl, addr, None))
            break
        hops.append((ttl, addr, rtt))
        if reached or addr == ip:
            break
        misses = misses + 1 if not addr else 0
        if misses >= 4:
            break
    return hops


def path_routers(ip: str, max_hops: int = 20, timeout_ms: int = 800, stop=None, exclude=()) -> list[str]:
    """Zwischenstationen (Router) bis zum Ziel, ohne das Ziel selbst und ohne eigene Adressen."""
    out: list[str] = []
    for _, addr, _ in traceroute(ip, max_hops, timeout_ms, stop):
        if addr and addr != ip and addr not in out and addr not in exclude:
            out.append(addr)
    return out
