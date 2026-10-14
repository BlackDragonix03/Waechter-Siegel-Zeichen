"""Startet NetGuard.

  python netguard.py                 Oberfläche
  python netguard.py --mcp           MCP-Server über Stdio (für Claude Desktop u. a.)
  python netguard.py --mcp-http 8765 MCP-Server über HTTP ohne Oberfläche (optional --token XYZ)
"""
import sys


def main() -> int:
    args = sys.argv[1:]
    if "--mcp" in args:
        from netguard.mcp.stdio_server import main as mcp_main
        return mcp_main()
    if "--mcp-http" in args:
        import time
        from netguard.mcp.backend import HeadlessBackend
        from netguard.mcp.http_server import McpHttpServer
        i = args.index("--mcp-http")
        port = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 8765
        token = args[args.index("--token") + 1] if "--token" in args and args.index("--token") + 1 < len(args) else ""
        host = "0.0.0.0" if "--lan" in args else "127.0.0.1"
        srv = McpHttpServer(HeadlessBackend(), port, host, token, lambda s: print(s, flush=True))
        srv.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            srv.stop()
        return 0
    from netguard.app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
