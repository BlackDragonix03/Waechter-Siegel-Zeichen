"""Speichern und Laden: Scans, bekannte Geräte, Einstellungen."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .model import Scan, Device


def data_dir() -> Path:
    """Datenordner neben der Exe (portabel), sonst im Benutzerprofil."""
    env = os.environ.get("NETGUARD_DATA")
    if env:
        p = Path(env)
    elif getattr(sys, "frozen", False):
        p = Path(sys.executable).resolve().parent / "NetGuard-Daten"
    else:
        base = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        p = Path(base) / "NetGuard"
    try:
        p.mkdir(parents=True, exist_ok=True)
        (p / "scans").mkdir(exist_ok=True)
    except OSError:
        p = Path.home() / "NetGuard"
        p.mkdir(parents=True, exist_ok=True)
        (p / "scans").mkdir(exist_ok=True)
    return p


def scans_dir() -> Path:
    return data_dir() / "scans"


def scan_path(scan: Scan) -> Path:
    stamp = scan.started.replace(":", "-").replace("T", "_")
    return scans_dir() / f"scan_{stamp}_{scan.id}.json"


def save_scan(scan: Scan, path: Path | None = None) -> Path:
    path = path or scan_path(scan)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(scan.to_dict(), fh, ensure_ascii=False, indent=1)
    tmp.replace(path)
    return path


def load_scan(path: Path) -> Scan:
    with Path(path).open("r", encoding="utf-8") as fh:
        return Scan.from_dict(json.load(fh))


def list_scans() -> list[tuple[Path, dict[str, Any]]]:
    """Alle gespeicherten Scans, neueste zuerst, mit Kurzinfo (ohne Geräte zu laden)."""
    items: list[tuple[Path, dict[str, Any]]] = []
    for p in sorted(scans_dir().glob("scan_*.json"), reverse=True):
        try:
            with p.open("r", encoding="utf-8") as fh:
                d = json.load(fh)
            items.append((p, {
                "id": d.get("id", ""),
                "name": d.get("name", ""),
                "started": d.get("started", ""),
                "targets": d.get("targets", []),
                "device_count": len(d.get("devices", [])),
                "problem_count": len(d.get("problems", [])),
            }))
        except (OSError, ValueError):
            continue
    return items


def delete_scan(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Bekannte Geräte: Benutzername, Notiz, vertrauenswürdig (Schlüssel = MAC/IP)
# ---------------------------------------------------------------------------
def known_path() -> Path:
    return data_dir() / "bekannte_geraete.json"


def load_known() -> dict[str, dict[str, Any]]:
    p = known_path()
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_known(known: dict[str, dict[str, Any]]) -> None:
    p = known_path()
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(known, fh, ensure_ascii=False, indent=1)
    tmp.replace(p)


def apply_known(devices: list[Device], known: dict[str, dict[str, Any]]) -> None:
    for d in devices:
        info = known.get(d.key)
        if not info:
            continue
        d.custom_name = info.get("custom_name", d.custom_name) or d.custom_name
        d.note = info.get("note", d.note) or d.note
        d.trusted = bool(info.get("trusted", d.trusted))
        if info.get("first_seen") and (not d.first_seen or info["first_seen"] < d.first_seen):
            d.first_seen = info["first_seen"]
        if info.get("device_type") and d.device_type == "unknown":
            d.device_type = info["device_type"]


def remember_device(known: dict[str, dict[str, Any]], d: Device) -> None:
    entry = known.setdefault(d.key, {})
    entry["custom_name"] = d.custom_name
    entry["note"] = d.note
    entry["trusted"] = d.trusted
    entry["device_type"] = d.device_type
    entry["last_ip"] = d.ip
    entry["last_name"] = d.any_name
    entry["first_seen"] = entry.get("first_seen") or d.first_seen or d.last_seen
    entry["last_seen"] = d.last_seen


# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------
def settings_path() -> Path:
    return data_dir() / "einstellungen.json"


def load_settings() -> dict[str, Any]:
    p = settings_path()
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_settings(s: dict[str, Any]) -> None:
    try:
        with settings_path().open("w", encoding="utf-8") as fh:
            json.dump(s, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass
