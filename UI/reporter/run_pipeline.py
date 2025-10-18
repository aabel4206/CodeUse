"""
End-to-end helpers for loading executor run records and producing concise
reporting artifacts (markdown tables + HTML galleries).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

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


def _extract_instruction(request_data: dict, notes: List[str]) -> Optional[str]:
    instruction = request_data.get("instruction") or request_data.get("prompt")
    if instruction:
        return str(instruction)

    arguments = request_data.get("arguments")
    if isinstance(arguments, list):
        for idx, argument in enumerate(arguments):
            if not isinstance(argument, str):
                continue
            if argument.startswith("--instruction"):
                if "=" in argument:
                    return argument.split("=", 1)[1].strip('"')
                if idx + 1 < len(arguments):
                    next_arg = arguments[idx + 1]
                    if isinstance(next_arg, str):
                        return next_arg.strip('"')
    elif isinstance(arguments, str) and arguments:
        return arguments

    for note in notes:
        if isinstance(note, str) and note.lower().startswith("instruction"):
            return note.split(":", 1)[-1].strip()
    return None


def _collect_screenshots(artifacts: List[dict], run_id: str) -> List[str]:
    screenshots: List[str] = []
    for artifact in artifacts:
        path = artifact.get("path")
        if not isinstance(path, str):
            continue
        lower = path.lower()
        if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            if path.startswith("runs/"):
                normalized = path[len("runs/") :]
            elif path.startswith(f"{run_id}/"):
                normalized = path
            else:
                normalized = f"{run_id}/{path}"
            screenshots.append(normalized)
    return screenshots


def _load_run_file(path: Path) -> RunSummary:
    data = json.loads(path.read_text())
    request_data = data.get("request", {})
    result_data = data.get("result", {})
    artifacts_data = data.get("artifacts", [])
    if not isinstance(artifacts_data, list):
        artifacts_data = []
    notes_source = data.get("notes", [])
    if not isinstance(notes_source, list):
        notes_source = [notes_source]
    notes = [str(item) for item in notes_source]

    inferred_run_id = data.get("run_id")
    if not inferred_run_id:
        if path.name == "result.json" and path.parent.name:
            inferred_run_id = path.parent.name
        else:
            inferred_run_id = path.stem

    instruction = _extract_instruction(request_data, notes)
    description = data.get("description") or result_data.get("description")
    if description is not None:
        description = str(description)
    next_prompt = data.get("next_prompt") or result_data.get("next_prompt")
    if next_prompt is not None:
        next_prompt = str(next_prompt)
    screenshots = _collect_screenshots(artifacts_data, str(inferred_run_id))
    primary_screenshot = screenshots[0] if screenshots else None

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
            for item in artifacts_data
            if isinstance(item, dict) and item.get("path")
        ],
        notes=notes,
        instruction=instruction,
        next_prompt=next_prompt,
        description=description,
        primary_screenshot=primary_screenshot,
        screenshots=screenshots,
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
