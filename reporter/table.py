"""
Utility helpers for rendering run summaries as Markdown tables.
"""

from __future__ import annotations

from typing import Iterable, List

from reporter.io_schemas import RunSummary

HEADERS = [
    "Run ID",
    "Tool",
    "Status",
    "Obs",
    "Errors",
    "Duration (s)",
    "Artifacts",
]


def _format_artifacts(summary: RunSummary) -> str:
    if not summary.artifacts:
        return "—"
    return "<br>".join(summary.artifacts)


def render_markdown_table(summaries: Iterable[RunSummary]) -> str:
    rows: List[List[str]] = []
    for summary in summaries:
        rows.append(
            [
                summary.run_id,
                summary.request.tool,
                summary.result.status,
                str(summary.result.observation_count),
                str(summary.result.error_count),
                f"{summary.result.duration_seconds:.2f}",
                _format_artifacts(summary),
            ]
        )

    if not rows:
        return "| No runs available |"

    header_line = "| " + " | ".join(HEADERS) + " |"
    separator_line = "| " + " | ".join("---" for _ in HEADERS) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator_line, *body_lines])
