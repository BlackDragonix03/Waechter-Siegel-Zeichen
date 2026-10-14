"""MCP über Stdio (für Claude Desktop und andere Clients, die den Server selbst starten).

Aufruf: NetGuard.exe --mcp   bzw.   python netguard.py --mcp
"""
from __future__ import annotations

import json
import sys

from .backend import HeadlessBackend
from .protocol import Session


def main() -> int:
    if sys.stdin is None or sys.stdout is None:
        try:
            sys.stderr.write("Keine Standardein-/ausgabe. Bitte NetGuard-MCP.exe --mcp verwenden (Konsolenversion).\n")
        except Exception:
            pass
        return 2
    backend = HeadlessBackend()
    session = Session(backend, lambda s: print(s, file=sys.stderr, flush=True))
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Ungültiges JSON"}}
        else:
            resp = session.handle(msg)
        if resp is not None:
            stdout.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            stdout.flush()
    return 0
