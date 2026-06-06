from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

TASKS: dict[str, dict[str, Any]] = {}
TASK_TTL_SECONDS = 60 * 60
TASK_TIMEOUT_SECONDS = int(os.getenv("TASK_TIMEOUT_SECONDS", "1800"))
TASK_STATE_PATH = Path(os.getenv("TASK_STATE_PATH", Path(__file__).resolve().parent / "task_state.json"))
_TASK_LOCK = threading.Lock()




def _persist_tasks() -> None:
    TASK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = TASK_STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(TASKS, sort_keys=True), encoding="utf-8")
    tmp_path.replace(TASK_STATE_PATH)


def load_task_state_on_startup() -> None:
    if not TASK_STATE_PATH.exists():
        return

    try:
        loaded = json.loads(TASK_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    if not isinstance(loaded, dict):
        return

    with _TASK_LOCK:
        TASKS.clear()
        for task_id, task in loaded.items():
            if not isinstance(task, dict):
                continue
            status = str(task.get("status", "pending"))
            restored = dict(task)
            if status in {"pending", "processing"}:
                restored["status"] = "failed"
                restored["error"] = "Task interrupted by server restart"
            TASKS[str(task_id)] = restored
        _prune_tasks()
        _persist_tasks()


def _prune_tasks(now: float | None = None) -> bool:
    current = now if now is not None else time.time()
    expired: list[str] = []
    for task_id, task in TASKS.items():
        created_at = float(task.get("created_at", 0))
        if current - created_at > TASK_TTL_SECONDS:
            expired.append(task_id)
    for task_id in expired:
        TASKS.pop(task_id, None)
    return bool(expired)


def _apply_timeout(task_id: str, task: dict[str, Any], now: float) -> bool:
    status = str(task.get("status", "pending"))
    if status not in {"pending", "processing"}:
        return False
    created_at = float(task.get("created_at", 0))
    if now - created_at <= TASK_TIMEOUT_SECONDS:
        return False
    task["status"] = "failed"
    task["error"] = "Task timed out"
    return True


def create_task(
    task_id: str,
    save_path: Path | None = None,
    safe_name: str | None = None,
    actual_size: int | None = None,
) -> None:
    with _TASK_LOCK:
        _prune_tasks()
        task: dict[str, Any] = {"status": "pending", "created_at": time.time(), "error": ""}
        if save_path is not None:
            task["save_path"] = str(save_path)
        if safe_name is not None:
            task["safe_name"] = safe_name
        if actual_size is not None:
            task["actual_size"] = int(actual_size)
        TASKS[task_id] = task
        _persist_tasks()


def set_task_status(task_id: str, status: str) -> None:
    with _TASK_LOCK:
        task = TASKS.get(task_id)
        if not task:
            TASKS[task_id] = {"status": status, "created_at": time.time(), "error": ""}
        else:
            task["status"] = status
        _persist_tasks()


def set_task_error(task_id: str, error: str) -> None:
    with _TASK_LOCK:
        task = TASKS.get(task_id)
        if not task:
            TASKS[task_id] = {"status": "failed", "created_at": time.time(), "error": error}
        else:
            task["error"] = error
        _persist_tasks()


def get_task_status(task_id: str) -> dict[str, Any] | None:
    with _TASK_LOCK:
        changed = _prune_tasks()
        task = TASKS.get(task_id)
        if not task:
            if changed:
                _persist_tasks()
            return None
        changed = _apply_timeout(task_id, task, time.time()) or changed
        if changed:
            _persist_tasks()
        return dict(task)
