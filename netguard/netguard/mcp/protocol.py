"""JSON-RPC-Verarbeitung nach dem Model Context Protocol (Version 2025-06-18, abwärtskompatibel)."""
from __future__ import annotations

import json
from typing import Any, Callable

from .. import APP_NAME, __version__
from .backend import Backend
from .tools import tool_descriptions, call_tool

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED = {"2024-11-05", "2025-03-26", "2025-06-18"}


class Session:
    """Verarbeitet Nachrichten eines Clients. Thread-sicher für unabhängige Aufrufe."""

    def __init__(self, backend: Backend, log: Callable[[str], None] | None = None):
        self.backend = backend
        self.log = log or (lambda s: None)
        self.initialized = False

    def handle(self, msg: Any) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Gibt die Antwort zurück, oder None bei Benachrichtigungen."""
        if isinstance(msg, list):
            out = [r for r in (self.handle(m) for m in msg) if r is not None]
            return out or None
        if not isinstance(msg, dict):
            return _error(None, -32600, "Ungültige Anfrage")
        mid = msg.get("id")
        method = msg.get("method")
        if method is None:
            return None   # Antwort des Clients
        params = msg.get("params") or {}
        if mid is None:
            self._notification(method, params)
            return None
        try:
            if method == "initialize":
                return _result(mid, self._initialize(params))
            if method == "ping":
                return _result(mid, {})
            if method == "tools/list":
                return _result(mid, {"tools": tool_descriptions()})
            if method == "tools/call":
                name = str(params.get("name", ""))
                args = params.get("arguments") or {}
                self.log(f"→ {name} {json.dumps(args, ensure_ascii=False)[:200]}")
                text, is_err = call_tool(self.backend, name, args)
                self.log(f"← {name}: {'FEHLER ' if is_err else ''}{text[:160]}{'…' if len(text) > 160 else ''}")
                return _result(mid, {"content": [{"type": "text", "text": text}], "isError": is_err})
            if method in ("resources/list", "resources/templates/list"):
                return _result(mid, {"resources": []} if method == "resources/list" else {"resourceTemplates": []})
            if method == "prompts/list":
                return _result(mid, {"prompts": []})
            if method == "logging/setLevel":
                return _result(mid, {})
            return _error(mid, -32601, f"Methode nicht unterstützt: {method}")
        except Exception as exc:
            return _error(mid, -32603, f"Interner Fehler: {exc!r}")

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        self.initialized = True
        wanted = str(params.get("protocolVersion", PROTOCOL_VERSION))
        version = wanted if wanted in SUPPORTED else PROTOCOL_VERSION
        client = params.get("clientInfo") or {}
        self.log(f"Client verbunden: {client.get('name', '?')} {client.get('version', '')} (Protokoll {version})")
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": APP_NAME, "version": __version__},
            "instructions": (
                "NetGuard scannt das lokale Netzwerk. Für eine aktuelle Übersicht scan_network aufrufen "
                "(dauert je nach Optionen 10 Sekunden bis mehrere Minuten); get_current_scan liefert den letzten Scan sofort. "
                "get_problems enthält Diagnose und Lösungsvorschläge."
            ),
        }

    def _notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "notifications/initialized":
            self.initialized = True


def _result(mid: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}
