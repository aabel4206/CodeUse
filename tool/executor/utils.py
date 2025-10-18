"""Utility helpers for the executor service."""

from __future__ import annotations

import datetime as _dt
import json
import uuid
from pathlib import Path
from typing import Any

RUNS_DIR = Path(__file__).resolve().parent / "runs"


def new_run_id() -> str:
    """Return a short unique identifier for a run."""
    return str(uuid.uuid4())[:8]


def run_path(run_id: str) -> Path:
    """Return the directory path for a run, ensuring it exists."""
    path = RUNS_DIR / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(obj: Any, path: str | Path) -> None:
    """Write the provided object to ``path`` as pretty-printed JSON."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def append_log(run_id: str, event: str, payload: Any) -> None:
    """Append an event record to the run log."""
    log_file = run_path(run_id) / "actions.jsonl"
    record = {
        "ts": _dt.datetime.utcnow().isoformat() + "Z",
        "event": event,
        "payload": payload,
    }
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
