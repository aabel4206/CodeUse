"""
End-to-end helpers for loading executor run records and producing concise
reporting artifacts (markdown tables + HTML galleries).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from reporter.gallery import build_gallery
from reporter.io_schemas import (
    ExecutionRequest,
    ExecutionResult,
    Observation,
    ReportArtifacts,
    RunError,
    RunSummary,
)
from reporter.table import render_markdown_table


def _parse_datetime(raw: str) -> datetime:
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.fromtimestamp(0)


def _load_run_file(path: Path) -> RunSummary:
    data = json.loads(path.read_text())
    request_data = data.get("request", {})
    result_data = data.get("result", {})
    inferred_run_id = data.get("run_id")
    if not inferred_run_id:
        if path.name == "result.json" and path.parent.name:
            inferred_run_id = path.parent.name
        else:
            inferred_run_id = path.stem

    return RunSummary(
        run_id=str(inferred_run_id),
        created_at=_parse_datetime(data.get("created_at", "1970-01-01T00:00:00+00:00")),
        request=ExecutionRequest(
            request_id=request_data.get("id", "unknown"),
            tool=request_data.get("tool", "unknown"),
            arguments=request_data.get("arguments", []),
            cwd=request_data.get("cwd", ""),
            timeout_ms=int(request_data.get("timeout_ms", 0)),
        ),
        result=ExecutionResult(
            status=result_data.get("status", "unknown"),
            exit_code=int(result_data.get("exit_code", -1)),
            duration_ms=int(result_data.get("duration_ms", 0)),
            started_at=_parse_datetime(
                result_data.get("started_at", "1970-01-01T00:00:00+00:00")
            ),
            finished_at=_parse_datetime(
                result_data.get("finished_at", "1970-01-01T00:05:00+00:00")
            ),
            highlights=[str(item) for item in result_data.get("highlights", [])],
            observations=[
                Observation.from_dict(item)
                for item in result_data.get("observations", [])
            ],
            errors=[RunError.from_dict(item) for item in result_data.get("errors", [])],
        ),
        artifacts=[
            str(item.get("path"))
            for item in data.get("artifacts", [])
            if isinstance(item, dict) and item.get("path")
        ],
        notes=[str(item) for item in data.get("notes", [])],
    )


def load_runs(runs_dir: Path) -> List[RunSummary]:
    if not runs_dir.exists():
        return []

    runs: List[RunSummary] = []
    for candidate in runs_dir.iterdir():
        if candidate.is_file() and candidate.suffix == ".json":
            target = candidate
        else:
            target = candidate / "result.json"
        if not target.exists():
            continue
        try:
            runs.append(_load_run_file(target))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {target}") from exc

    runs.sort(key=lambda run: run.created_at, reverse=True)
    return runs


def generate_report(summaries: Iterable[RunSummary]) -> ReportArtifacts:
    summaries_list = list(summaries)
    return ReportArtifacts(
        table_markdown=render_markdown_table(summaries_list),
        gallery_html=build_gallery(summaries_list),
    )
