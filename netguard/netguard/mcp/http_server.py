"""MCP über Streamable HTTP: POST /mcp mit JSON-RPC, Antwort als JSON. Zum Ein- und Ausschalten."""
from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import urlparse

from .. import APP_NAME, __version__
from .backend import Backend
from .protocol import Session


class McpHttpServer:
    def __init__(self, backend: Backend, port: int = 8765, host: str = "127.0.0.1", token: str = "",
                 log: Callable[[str], None] | None = None):
        self.backend = backend
        self.port = port
        self.host = host
        self.token = token
        self.log = log or (lambda s: None)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.session = Session(backend, self.log)
        self.session_id = secrets.token_hex(8)

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        host = "127.0.0.1" if self.host in ("", "0.0.0.0") else self.host
        return f"http://{host}:{self.port}/mcp"

    def start(self) -> None:
        if self._server is not None:
            return
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"{APP_NAME}/{__version__}"
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # ruhig
                pass

            def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Mcp-Session-Id", outer.session_id)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Mcp-Session-Id, MCP-Protocol-Version, Accept")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
                self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self) -> bool:
                # Schutz gegen DNS-Rebinding: nur lokale Origins
                origin = self.headers.get("Origin", "")
                if origin:
                    host = urlparse(origin).hostname or ""
                    if host not in ("localhost", "127.0.0.1", "::1") and outer.host in ("127.0.0.1", "localhost"):
                        return False
                if outer.token:
                    auth = self.headers.get("Authorization", "")
                    tok = auth[7:].strip() if auth.lower().startswith("bearer ") else self.headers.get("X-Api-Key", "")
                    if tok != outer.token:
                        return False
                return True

            def do_OPTIONS(self):
                self._send(204, b"", "text/plain")

            def do_GET(self):
                path = urlparse(self.path).path
                if path in ("/", "/info"):
                    info = {"name": APP_NAME, "version": __version__, "mcp_endpoint": outer.url, "transport": "streamable-http",
                            "auth": "Bearer-Token nötig" if outer.token else "kein Token (nur lokal)",
                            "tools": [t["name"] for t in __import__("netguard.mcp.tools", fromlist=["tool_descriptions"]).tool_descriptions()]}
                    self._send(200, json.dumps(info, ensure_ascii=False, indent=1).encode("utf-8"))
                    return
                if path == "/mcp":
                    # Kein Server-zu-Client-Stream nötig
                    self._send(405, b'{"error":"Nur POST wird unterstuetzt"}')
                    return
                self._send(404, b'{"error":"nicht gefunden"}')

            def do_DELETE(self):
                self._send(200, b"{}")

            def do_POST(self):
                path = urlparse(self.path).path
                if path not in ("/mcp", "/"):
                    self._send(404, b'{"error":"nicht gefunden"}')
                    return
                if not self._authorized():
                    self._send(401, b'{"error":"nicht autorisiert"}')
                    return
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    msg = json.loads(raw.decode("utf-8")) if raw else None
                except ValueError:
                    self._send(400, json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Ungültiges JSON"}}).encode())
                    return
                resp = outer.session.handle(msg)
                if resp is None:
                    self._send(202, b"", "text/plain")
                    return
                self._send(200, json.dumps(resp, ensure_ascii=False).encode("utf-8"))

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.log(f"MCP-Server läuft: {self.url}" + (" (Token nötig)" if self.token else ""))

    def stop(self) -> None:
        if self._server is None:
            return
        srv = self._server
        self._server = None
        srv.shutdown()
        srv.server_close()
        self.log("MCP-Server gestoppt.")
