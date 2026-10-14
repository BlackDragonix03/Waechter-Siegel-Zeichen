"""Anbindung an Ollama (http://127.0.0.1:11434): Modelle auflisten, laden, Chat mit Tool-Aufrufen."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_URL = "http://127.0.0.1:11434"

# (Modellname bei Ollama, Anzeige, ungefähre Downloadgröße, Hinweis)
SUGGESTED_MODELS: list[tuple[str, str, str, str]] = [
    ("qwen2.5:0.5b", "Qwen 2.5 0.5B", "0,4 GB", "sehr klein, nur einfache Fragen, Tool-Aufrufe unzuverlässig"),
    ("llama3.2:1b", "Llama 3.2 1B", "1,3 GB", "klein, schnell, einfache Zusammenfassungen"),
    ("qwen2.5:1.5b", "Qwen 2.5 1.5B", "1,0 GB", "klein, kann Tools meist aufrufen"),
    ("qwen2.5:3b", "Qwen 2.5 3B", "1,9 GB", "empfohlen: gutes Deutsch, Tool-Aufrufe funktionieren"),
    ("llama3.2:3b", "Llama 3.2 3B", "2,0 GB", "gut, Tool-Aufrufe funktionieren"),
    ("phi3.5:3.8b", "Phi 3.5 Mini 3.8B", "2,2 GB", "gut im Erklären, Tool-Aufrufe schwächer"),
    ("gemma3:4b", "Gemma 3 4B", "3,3 GB", "stärkstes der kleinen Modelle, braucht mehr RAM"),
]


@dataclass
class ModelInfo:
    name: str
    size_bytes: int
    modified: str


def _request(url: str, data: dict | None = None, timeout: float = 10.0, stream: bool = False):
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8") if data is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "NetGuard"},
                                 method="POST" if data is not None else "GET")
    return urllib.request.urlopen(req, timeout=timeout)


def available(base: str = DEFAULT_URL) -> tuple[bool, str]:
    """Ist Ollama erreichbar? Rückgabe (ja/nein, Version oder Fehlertext)."""
    try:
        with _request(base.rstrip("/") + "/api/version", timeout=3.0) as resp:
            v = json.loads(resp.read().decode("utf-8")).get("version", "?")
            return True, str(v)
    except urllib.error.URLError as exc:
        return False, f"Ollama nicht erreichbar ({exc.reason}). Installieren von https://ollama.com, danach läuft es im Hintergrund."
    except Exception as exc:
        return False, f"Ollama nicht erreichbar ({exc})."


def list_models(base: str = DEFAULT_URL) -> list[ModelInfo]:
    with _request(base.rstrip("/") + "/api/tags", timeout=5.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [ModelInfo(m.get("name", ""), int(m.get("size", 0) or 0), m.get("modified_at", "")) for m in data.get("models", [])]


def pull_model(name: str, base: str = DEFAULT_URL, progress: Callable[[str, int, int], None] | None = None,
               stop: Callable[[], bool] | None = None) -> bool:
    """Lädt ein Modell. progress(status, fertig_bytes, gesamt_bytes)."""
    with _request(base.rstrip("/") + "/api/pull", {"name": name, "stream": True}, timeout=3600.0, stream=True) as resp:
        for raw in resp:
            if stop is not None and stop():
                return False
            try:
                d = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            if "error" in d:
                raise RuntimeError(d["error"])
            if progress is not None:
                progress(str(d.get("status", "")), int(d.get("completed", 0) or 0), int(d.get("total", 0) or 0))
            if d.get("status") == "success":
                return True
    return True


def delete_model(name: str, base: str = DEFAULT_URL) -> None:
    req = urllib.request.Request(base.rstrip("/") + "/api/delete", data=json.dumps({"name": name}).encode(),
                                 headers={"Content-Type": "application/json"}, method="DELETE")
    urllib.request.urlopen(req, timeout=30).read()


# ---------------------------------------------------------------------------
# Chat mit Tool-Aufrufen
# ---------------------------------------------------------------------------
def tools_for_ollama(descriptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}}
            for t in descriptions]


def chat(messages: list[dict[str, Any]], model: str, tools: list[dict[str, Any]] | None, call_tool: Callable[[str, dict], tuple[str, bool]],
         base: str = DEFAULT_URL, max_rounds: int = 8, on_event: Callable[[str, str], None] | None = None,
         stop: Callable[[], bool] | None = None, timeout: float = 600.0) -> str:
    """Führt ein Gespräch mit Tool-Schleife. messages wird um Antworten/Tool-Ergebnisse ergänzt.

    on_event(art, text): "tool" (Aufruf), "result" (Ergebnis), "text" (Antwort).
    """
    ev = on_event or (lambda a, t: None)
    for _ in range(max_rounds):
        if stop is not None and stop():
            return "(abgebrochen)"
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.2, "num_ctx": 8192}}
        if tools:
            body["tools"] = tools
        try:
            with _request(base.rstrip("/") + "/api/chat", body, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            if tools and ("does not support tools" in detail or exc.code == 400):
                # Modell ohne Tool-Unterstützung: ohne Tools weiter
                tools = None
                ev("text", "(Dieses Modell kann keine Werkzeuge aufrufen; antworte nur aus dem Wissen des Modells.)")
                continue
            raise RuntimeError(f"Ollama-Fehler {exc.code}: {detail}")
        msg = data.get("message") or {}
        calls = msg.get("tool_calls") or []
        messages.append({"role": "assistant", "content": msg.get("content", "") or "", **({"tool_calls": calls} if calls else {})})
        if not calls:
            text = (msg.get("content") or "").strip()
            ev("text", text)
            return text
        for c in calls:
            fn = (c.get("function") or {})
            name = str(fn.get("name", ""))
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            ev("tool", f"{name} {json.dumps(args, ensure_ascii=False)}")
            text, is_err = call_tool(name, args)
            if len(text) > 12000:
                text = text[:12000] + " …(gekürzt)"
            ev("result", ("FEHLER: " if is_err else "") + text[:300])
            messages.append({"role": "tool", "content": text, "tool_name": name})
    return "(Zu viele Werkzeug-Runden, abgebrochen.)"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"

