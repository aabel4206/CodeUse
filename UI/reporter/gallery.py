"""
Generate lightweight HTML fragments that highlight every observation discovered
in the latest executor run.

The gallery output is intentionally self-contained so presenters can drop the
markup straight into a slide deck or `iframe` demo without needing a build
step.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, List

from reporter.io_schemas import Observation, RunSummary


def _normalize_path(path: str | None) -> str | None:
    if not path:
        return None
    return path.replace("\\", "/")


def _render_issue_card(summary: RunSummary, observation: Observation, fallback: str | None) -> str:
    screenshot_path = _normalize_path(observation.screenshot or fallback)
    if screenshot_path:
        screenshot_html = (
            '<figure class="issue-screenshot">'
            f'<img src="{escape(screenshot_path)}" alt="Screenshot for {escape(summary.run_id)}" loading="lazy" />'
            "</figure>"
        )
    else:
        screenshot_html = '<div class="issue-screenshot placeholder">No screenshot available.</div>'

    body: List[str] = [
        f'<p class="issue-message"><span class="severity severity-{escape(observation.severity)}">'
        f"{escape(observation.severity.title())}</span> {escape(observation.message)}</p>"
    ]
    if observation.selector:
        body.append(f'<p class="issue-selector">Selector: <code>{escape(observation.selector)}</code></p>')
    if observation.description:
        body.append(f'<p class="issue-description">{escape(observation.description)}</p>')
    if observation.suggested_prompt:
        body.append(
            f'<p class="issue-prompt"><strong>Suggested prompt:</strong> '
            f"{escape(observation.suggested_prompt)}</p>"
        )

    return (
        '<article class="issue-card">'
        f"{screenshot_html}"
        '<div class="issue-body">'
        f"{''.join(body)}"
        "</div>"
        "</article>"
    )


def build_gallery(summaries: Iterable[RunSummary]) -> str:
    summaries_list = list(summaries)
    if not summaries_list:
        return (
            '<section class="issue-gallery empty">'
            "<style>.issue-gallery{font-family:system-ui;color:#e2e8f0;background:#0f172a;"
            "padding:2rem;border-radius:0.75rem;text-align:center;}</style>"
            "<p>No runs to display.</p>"
            "</section>"
        )

    summary = summaries_list[0]

    fallback_screens = summary.screenshots or ([summary.primary_screenshot] if summary.primary_screenshot else [])
    fallback_screens = [_normalize_path(path) for path in fallback_screens if path]

    if summary.result.observations:
        issue_cards = []
        for idx, observation in enumerate(summary.result.observations):
            fallback = fallback_screens[idx % len(fallback_screens)] if fallback_screens else None
            issue_cards.append(_render_issue_card(summary, observation, fallback))
    else:
        issue_cards = [
            '<article class="issue-card">'
            '<div class="issue-screenshot placeholder">No issues detected.</div>'
            "<p class=\"issue-description\">The latest run did not surface any observations.</p>"
            "</article>"
        ]

    highlights = "".join(f"<li>{escape(item)}</li>" for item in summary.result.highlights) or "<li>No highlights.</li>"
    notes = "".join(f"<li>{escape(item)}</li>" for item in summary.notes) or "<li>No additional notes.</li>"

    instruction_text = summary.instruction or "No instruction recorded."
    next_prompt_text = summary.next_prompt or "No follow-up prompt suggested yet."

    return (
        '<section class="issue-gallery">'
        "<style>"
        "body{margin:0;background:#0f172a;overflow:hidden;font-family:system-ui;}"
        ".issue-gallery{color:#e2e8f0;background:#0f172a;min-height:100vh;width:100vw;"
        "display:flex;flex-direction:column;gap:1rem;box-sizing:border-box;padding:1rem;}"
        ".run-header{display:flex;flex-direction:column;gap:0.35rem;}"
        ".run-header h2{margin:0;font-size:1.6rem;}"
        ".run-header .meta{display:flex;flex-wrap:wrap;gap:1rem;font-size:0.9rem;color:#cbd5f5;}"
        ".run-header .meta span{display:flex;align-items:center;gap:0.35rem;}"
        ".run-header .summary-text{margin:0;font-size:0.95rem;line-height:1.4;color:#e2e8f0;}"
        ".issue-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(17rem,1fr));gap:1rem;flex:1;}"
        ".issue-card{background:#1e293b;display:flex;flex-direction:column;overflow:hidden;"
        "border-radius:0;box-shadow:none;}"
        ".issue-body{padding:0.9rem 1rem 1rem;display:flex;flex-direction:column;gap:0.45rem;font-size:0.92rem;line-height:1.35;}"
        ".issue-screenshot{margin:0;height:12rem;}"
        ".issue-screenshot img{width:100%;height:100%;object-fit:cover;display:block;}"
        ".issue-screenshot.placeholder{color:#94a3b8;font-size:0.95rem;}"
        ".issue-message{margin:0;font-size:0.95rem;line-height:1.35;color:#e2e8f0;}"
        ".issue-selector{margin:0;font-size:0.8rem;color:#cbd5f5;}"
        ".issue-description{margin:0;font-size:0.85rem;line-height:1.4;color:#f8fafc;}"
        ".issue-prompt{margin:0;font-size:0.85rem;color:#e0f2fe;}"
        ".severity{padding:0.2rem 0.5rem;border-radius:9999px;font-size:0.65rem;text-transform:uppercase;"
        "letter-spacing:0.05em;}"
        ".severity-info{background:rgba(14,165,233,0.25);color:#38bdf8;}"
        ".severity-warning{background:rgba(245,158,11,0.25);color:#fbbf24;}"
        ".severity-error{background:rgba(239,68,68,0.25);color:#fca5a5;}"
        ".run-notes{background:#1e293b;padding:1rem;border-radius:0;box-shadow:none;font-size:0.9rem;line-height:1.4;}"
        ".run-notes h3{margin:0 0 0.4rem 0;font-size:1rem;color:#bfdbfe;}"
        ".run-notes ul{margin:0;padding-left:1.1rem;}"
        "</style>"
        f"<header class='run-header'>"
        f"<h2>Run {escape(summary.run_id)}</h2>"
        "<div class='meta'>"
        f"<span><strong>Tool:</strong> {escape(summary.request.tool)}</span>"
        f"<span><strong>Status:</strong> {escape(summary.result.status)}</span>"
        f"<span><strong>Duration:</strong> {summary.result.duration_seconds:.2f}s</span>"
        f"<span><strong>Exit code:</strong> {summary.result.exit_code}</span>"
        "</div>"
        f"<p class='summary-text'><strong>Instruction:</strong> {escape(instruction_text)}</p>"
        f"<p class='summary-text'><strong>Next prompt:</strong> {escape(next_prompt_text)}</p>"
        "</header>"
        f"<div class='issue-grid'>{''.join(issue_cards)}</div>"
        "<section class='run-notes'>"
        "<h3>Highlights</h3>"
        f"<ul>{highlights}</ul>"
        "<h3>Notes</h3>"
        f"<ul>{notes}</ul>"
        "</section>"
        "</section>"
    )
