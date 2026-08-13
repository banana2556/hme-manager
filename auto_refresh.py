"""Keep-alive worker for the imported iCloud session.

Runs a low-risk /v2/hme/list check on a fixed interval so the cookie session
stays warm. Auth-style failures (401/403/421) disable the worker and flag the
session for re-import instead of hammering Apple with a dead cookie.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from hme import HmeError

DEFAULT_INTERVAL_SECONDS = 600
MIN_INTERVAL_SECONDS = 300
_POLL_SECONDS = 30
_AUTH_ERROR_MARKERS = ("HTTP 401", "HTTP 403", "HTTP 421")

_STOP = threading.Event()
_THREAD: threading.Thread | None = None


def config_path(manager: Any) -> Path:
    return Path(manager.state_dir) / "auto-refresh.json"


def defaults() -> dict[str, Any]:
    return {
        "enabled": True,
        "intervalSeconds": DEFAULT_INTERVAL_SECONDS,
        "lastRunAt": None,
        "lastSuccessAt": None,
        "lastDisabledAt": None,
        "lastError": None,
        "disabledReason": None,
    }


def _normalize(config: dict[str, Any]) -> dict[str, Any]:
    merged = {**defaults(), **config}
    try:
        merged["intervalSeconds"] = max(
            MIN_INTERVAL_SECONDS,
            int(merged.get("intervalSeconds") or DEFAULT_INTERVAL_SECONDS),
        )
    except (TypeError, ValueError):
        merged["intervalSeconds"] = DEFAULT_INTERVAL_SECONDS
    merged["enabled"] = bool(merged.get("enabled"))
    return merged


def load_config(manager: Any) -> dict[str, Any]:
    path = config_path(manager)
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}
    return _normalize(data)


def save_config(config: dict[str, Any], manager: Any) -> dict[str, Any]:
    merged = _normalize(config)
    path = config_path(manager)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged


def status(manager: Any) -> dict[str, Any]:
    config = load_config(manager)
    config["workerRunning"] = _THREAD is not None and _THREAD.is_alive()
    now = time.time()
    interval = config["intervalSeconds"]
    last_run = float(config.get("lastRunAt") or config.get("lastSuccessAt") or 0)
    if config.get("enabled"):
        next_run_at = (last_run + interval) if last_run else now + interval
        config["remainingSeconds"] = max(0, int(round(next_run_at - now)))
        config["nextRunAt"] = next_run_at
    else:
        config["remainingSeconds"] = None
        config["nextRunAt"] = None
    config["serverNow"] = now
    return config


def update(payload: Mapping[str, Any], manager: Any) -> dict[str, Any]:
    current = load_config(manager)
    if "enabled" in payload:
        current["enabled"] = bool(payload.get("enabled"))
        if current["enabled"]:
            current["disabledReason"] = None
            current["lastDisabledAt"] = None
            current["lastError"] = None
    if "intervalSeconds" in payload:
        current["intervalSeconds"] = payload.get("intervalSeconds")
    return save_config(current, manager)


def disable(reason: str, manager: Any) -> dict[str, Any]:
    current = load_config(manager)
    current.update({"enabled": False, "lastDisabledAt": time.time(), "disabledReason": reason, "lastError": reason})
    return save_config(current, manager)


def _requires_disable(session_status: dict[str, Any]) -> str | None:
    if not isinstance(session_status, dict):
        return None
    if session_status.get("needsReauth"):
        return "session requires re-import"
    error = str(session_status.get("lastError") or "")
    if any(marker in error for marker in _AUTH_ERROR_MARKERS):
        return error
    return None


def run_once(manager: Any) -> dict[str, Any]:
    now = time.time()
    config = load_config(manager)
    config["lastRunAt"] = now
    try:
        session_status = manager.check()
    except HmeError as exc:
        reason = str(exc)
        if any(marker in reason for marker in _AUTH_ERROR_MARKERS):
            return {"autoRefresh": disable(reason, manager), "session": None}
        config["lastError"] = reason
        return {"autoRefresh": save_config(config, manager), "session": None}
    reason = _requires_disable(session_status)
    if reason:
        return {"autoRefresh": disable(reason, manager), "session": session_status}
    config.update({"lastSuccessAt": now, "lastError": None, "disabledReason": None})
    return {"autoRefresh": save_config(config, manager), "session": session_status}


def _loop(manager: Any) -> None:
    while not _STOP.is_set():
        try:
            config = load_config(manager)
            if config.get("enabled"):
                last_run = float(config.get("lastRunAt") or 0)
                if time.time() - last_run >= config["intervalSeconds"]:
                    run_once(manager)
        except Exception as exc:  # never let an unexpected error kill the worker
            print(f"auto-refresh worker error: {exc}")
        _STOP.wait(_POLL_SECONDS)


def start_worker(manager: Any) -> None:
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, args=(manager,), name="hme-auto-refresh", daemon=True)
    _THREAD.start()


def stop_worker() -> None:
    _STOP.set()
    if _THREAD is not None:
        _THREAD.join(timeout=5)
