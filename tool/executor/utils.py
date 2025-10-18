"""Utility helpers for the executor service."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


def new_run_id() -> str:
    """Return a short unique identifier for a run."""
    return str(uuid.uuid4())[:8]


def save_json(obj: Any, path: str | Path) -> None:
    """Write the provided object to ``path`` as pretty-printed JSON."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
