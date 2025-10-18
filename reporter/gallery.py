"""
Generate lightweight HTML fragments that showcase recent executor runs.

The gallery output is intentionally self-contained so presenters can drop the
markup straight into a slide deck or `iframe` demo without needing a build
step.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, List

from reporter.io_schemas import RunSummary


def build_gallery(summaries: Iterable[RunSummary]) -> str:
    cards: List[str] = []
    for summary in summaries:
        highlights = "".join(
            f"<li>{escape(item)}</li>" for item in summary.result.highlights
        ) or "<li>No highlights captured.</li>"
        notes = "".join(f"<li>{escape(item)}</li>" for item in summary.notes) or "<li>No extra notes.</li>"
        observations = "".join(
            f"<li><code>{escape(obs.selector or '*')}</code> · "
            f"<span class=\"severity severity-{escape(obs.severity)}\">{escape(obs.severity.title())}</span> "
            f"{escape(obs.message)}</li>"
            for obs in summary.result.observations
        ) or "<li>No observations logged.</li>"
        errors = "".join(
            f"<li><strong>{escape(err.code or 'Error')}</strong> · {escape(err.message)}</li>"
            for err in summary.result.errors
        ) or "<li>No errors.</li>"
        cards.append(
            (
                '<article class="card">'
                f"<h3>{escape(summary.run_id)}</h3>"
                f"<p><strong>{escape(summary.request.tool)}</strong> → "
                f"{escape(summary.result.status)}</p>"
                f"<p>Duration: {summary.result.duration_seconds:.2f}s</p>"
                f"<p>Exit code: {summary.result.exit_code}</p>"
                f"<section><h4>Highlights</h4><ul class=\"highlights\">{highlights}</ul></section>"
                f"<section><h4>Observations</h4><ul class=\"observations\">{observations}</ul></section>"
                f"<section><h4>Errors</h4><ul class=\"errors\">{errors}</ul></section>"
                f"<section><h4>Notes</h4><ul class=\"notes\">{notes}</ul></section>"
                "</article>"
            )
        )

    if not cards:
        cards.append("<p>No runs to display.</p>")

    return (
        "<section class=\"run-gallery\">"
        "<style>"
        ".run-gallery{display:flex;gap:1rem;flex-wrap:wrap;font-family:system-ui;"
        "background:#0f172a;color:#e2e8f0;padding:1rem;border-radius:0.75rem;}"
        ".run-gallery .card{background:#1e293b;padding:1rem;border-radius:0.5rem;"
        "box-shadow:0 4px 10px rgba(0,0,0,0.3);width:18rem;}"
        ".run-gallery h3{margin-top:0;font-size:1rem;}"
        ".run-gallery section{margin-bottom:0.75rem;}"
        ".run-gallery h4{margin:0 0 0.25rem 0;font-size:0.85rem;color:#93c5fd;}"
        ".run-gallery ul{padding-left:1.1rem;margin:0.25rem 0;}"
        ".run-gallery code{background:rgba(148,163,184,0.2);padding:0 0.25rem;"
        "border-radius:0.25rem;font-size:0.75rem;}"
        ".run-gallery .severity{padding:0 0.35rem;border-radius:9999px;margin-right:0.35rem;"
        "font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;}"
        ".run-gallery .severity-info{background:rgba(14,165,233,0.25);color:#38bdf8;}"
        ".run-gallery .severity-warning{background:rgba(245,158,11,0.25);color:#fbbf24;}"
        ".run-gallery .severity-error{background:rgba(239,68,68,0.25);color:#fca5a5;}"
        "</style>"
        f"{''.join(cards)}"
        "</section>"
    )
