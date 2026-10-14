"""TCP-Port-Prüfung und einfache Dienst-Erkennung (HTTP-Titel, SSH-Banner)."""
from __future__ import annotations

import re
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor

# Port -> Dienstname
SERVICES: dict[int, str] = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP", 81: "HTTP (alt)",
    88: "Kerberos", 110: "POP3", 135: "RPC (Windows)", 139: "NetBIOS", 143: "IMAP", 161: "SNMP",
    443: "HTTPS", 445: "SMB (Dateifreigabe)", 515: "LPD (Drucker)", 548: "AFP (Apple)",
    554: "RTSP (Kamera-Stream)", 587: "SMTP (Submission)", 631: "IPP (Drucker)", 853: "DNS über TLS",
    993: "IMAPS", 995: "POP3S", 1080: "SOCKS", 1400: "Sonos", 1433: "MS-SQL", 1883: "MQTT",
    1900: "UPnP", 2049: "NFS", 2222: "SSH (alt)", 3000: "Web (3000)", 3283: "Apple Remote Desktop",
    3306: "MySQL", 3389: "Remotedesktop (RDP)", 5000: "Web (5000) / Synology", 5001: "Synology HTTPS",
    5353: "mDNS", 5357: "WSD (Windows)", 5432: "PostgreSQL", 5555: "ADB (Android)", 5900: "VNC",
    6379: "Redis", 7000: "AirPlay", 7070: "RTSP (alt)", 8000: "Web (8000)", 8006: "Proxmox",
    8008: "Chromecast", 8009: "Chromecast / AJP", 8080: "HTTP (8080)", 8081: "Web (8081)",
    8086: "InfluxDB", 8123: "Home Assistant", 8443: "HTTPS (8443)", 8883: "MQTT (TLS)",
    9000: "Web (9000) / Portainer", 9090: "Web (9090)", 9100: "Drucker (Raw/JetDirect)",
    9443: "HTTPS (9443)", 32400: "Plex", 49152: "UPnP (alt)", 62078: "iPhone-Sync",
}

QUICK_PORTS = [22, 23, 53, 80, 135, 139, 443, 445, 515, 554, 631, 3389, 5000, 8080, 8443, 9100, 62078]
FULL_PORTS = sorted(SERVICES.keys())


def check_port(ip: str, port: int, timeout: float = 0.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def scan_ports(ip: str, ports: list[int], timeout: float = 0.5, workers: int = 32) -> list[int]:
    open_ports: list[int] = []
    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(ports)))) as ex:
        for port, ok in zip(ports, ex.map(lambda p: check_port(ip, p, timeout), ports)):
            if ok:
                open_ports.append(port)
    return sorted(open_ports)


def service_name(port: int) -> str:
    return SERVICES.get(port, f"Port {port}")


def http_title(ip: str, port: int, timeout: float = 2.0) -> tuple[str, str]:
    """Holt Titel und Server-Header einer Weboberfläche. Rückgabe (Titel, Server)."""
    https = port in (443, 8443, 5001, 9443, 8006)
    try:
        raw = socket.create_connection((ip, port), timeout=timeout)
        if https:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(raw, server_hostname=ip)
        else:
            sock = raw
        sock.settimeout(timeout)
        sock.sendall(f"GET / HTTP/1.0\r\nHost: {ip}\r\nUser-Agent: NetGuard\r\nConnection: close\r\n\r\n".encode())
        chunks = []
        total = 0
        while total < 65536:
            try:
                c = sock.recv(8192)
            except (socket.timeout, OSError):
                break
            if not c:
                break
            chunks.append(c)
            total += len(c)
        sock.close()
    except (OSError, ssl.SSLError):
        return "", ""
    body = b"".join(chunks).decode("utf-8", errors="replace")
    server = ""
    m = re.search(r"^Server:\s*(.+?)\r?$", body, re.I | re.M)
    if m:
        server = m.group(1).strip()
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        title = re.sub(r"&amp;", "&", title)
    if not title:
        m = re.search(r"^Location:\s*(.+?)\r?$", body, re.I | re.M)
        if m:
            title = "→ " + m.group(1).strip()
    return title[:80], server[:60]


def banner(ip: str, port: int, timeout: float = 1.5) -> str:
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        s.settimeout(timeout)
        data = s.recv(200)
        s.close()
        return data.decode("utf-8", errors="replace").strip().splitlines()[0][:80] if data else ""
    except (OSError, IndexError):
        return ""
