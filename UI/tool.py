"""
CLI entry point for the CodeUse reporter/demo role (Person D).

Capabilities:
    python tool.py run --instruction "Fix hover animation"
        Executes a run against the orchestrator (or a local mock) and stores
        artifacts inside runs/<id>/.

    python tool.py report
        Aggregates every stored run and prints the consolidated table while
        exporting overview files (runs/overview.md, runs/gallery.html).

    python tool.py demo
        Shortcut for `run` in mock mode with a pre-filled instruction that
        mirrors the showcase scenario.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Tuple

from reporter import generate_report, load_runs
from reporter.io_schemas import Observation, RunError

ROOT = Path(__file__).parent
RUNS_DIR = ROOT / "runs"
DEFAULT_HOST = "http://localhost:8000"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _request_json(url: str, *, payload: dict | None = None, method: str = "GET") -> dict:
    headers = {"Content-Type": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_markdown_table(headers: List[str], rows: Iterable[Iterable[str]]) -> str:
    rows = [list(row) for row in rows]
    if not rows:
        return ""
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator_line, *body_lines])


def _open_gallery_in_browser(gallery_path: Path, open_browser: bool) -> None:
    if not open_browser:
        return
    try:
        resolved = gallery_path.resolve()
    except FileNotFoundError:
        return
    if resolved.exists():
        webbrowser.open(resolved.as_uri(), new=1)


# ---------------------------------------------------------------------------
# Run generation (live + mock)
# ---------------------------------------------------------------------------


def _trigger_live_run(
    instruction: str,
    *,
    host: str,
    poll_interval: float,
    max_polls: int,
) -> dict:
    base = host.rstrip("/")
    task_response = _request_json(
        f"{base}/tasks",
        payload={"instruction": instruction},
        method="POST",
    )
    run_id = (
        task_response.get("run_id")
        or task_response.get("id")
        or task_response.get("task_id")
    )
    if not run_id:
        raise ValueError("Orchestrator response missing run identifier.")

    for _ in range(max_polls):
        time.sleep(poll_interval)
        run_snapshot = _request_json(f"{base}/runs/{run_id}")
        result = run_snapshot.get("result", {})
        status = result.get("status") or run_snapshot.get("status")
        if status and status.lower() in TERMINAL_STATUSES:
            run_snapshot.setdefault("run_id", run_id)
            run_snapshot.setdefault("created_at", run_snapshot.get("queued_at", _now().isoformat()))
            run_snapshot.setdefault("request", {"id": task_response.get("task_id", str(uuid.uuid4()))})
            return run_snapshot

    raise TimeoutError(f"Timed out polling run {run_id!r} from orchestrator.")


def _build_mock_run(instruction: str) -> dict:
    started_at = _now()
    duration_ms = 4875
    finished_at = started_at + timedelta(milliseconds=duration_ms)
    run_id = f"mock-{started_at.strftime('%Y%m%d-%H%M%S')}"
    observations = [
        {
            "selector": ".hero__cta",
            "severity": "error",
            "message": "Primary call-to-action collides with hero copy on desktop.",
            "description": "At 1440px width the CTA button overlaps the heading, obscuring the main marketing message.",
            "screenshot": f"runs/{run_id}/artifacts/issue-hero-overlap.png",
            "suggested_prompt": "Adjust the hero layout so the CTA sits below the heading with responsive spacing.",
        },
        {
            "selector": "footer a[href*=\"contact\"]",
            "severity": "warning",
            "message": "Footer contact link color fails contrast requirements against background.",
            "description": "The contact link uses #5D9CEC on a light gradient, yielding a 2.1:1 contrast ratio.",
            "screenshot": f"runs/{run_id}/artifacts/issue-footer-contrast.png",
            "suggested_prompt": "Apply a darker footer link color or background to meet at least 4.5:1 contrast.",
        },
        {
            "selector": ".nav__menu-toggle",
            "severity": "info",
            "message": "Mobile nav toggle lacks accessible name.",
            "description": "Screen readers announce the toggle as 'button' with no label; aria-label should describe the action.",
            "screenshot": f"runs/{run_id}/artifacts/issue-nav-toggle.png",
            "suggested_prompt": "Add aria-label=\"Open navigation\" to the mobile menu toggle button.",
        },
    ]
    payload = {
        "run_id": run_id,
        "created_at": started_at.isoformat(),
        "instruction": instruction,
        "description": "Baseline audit of ntedvs.com capturing layout, accessibility, and contrast problems.",
        "next_prompt": "Fix the highlighted issues on ntedvs.com and re-run the audit to verify the fixes.",
        "request": {
            "id": str(uuid.uuid4()),
            "tool": "codeuse-cli",
            "arguments": ["run", f'--instruction="{instruction}"', "--mode=mock"],
            "cwd": str(ROOT.resolve()),
            "timeout_ms": 600000,
        },
        "result": {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": duration_ms,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "highlights": [
                "Executor replayed hover interaction on Chromium demo page.",
                "Link contrast analysis captured footer accessibility issues.",
            ],
            "observations": observations,
            "errors": [],
            "description": "Baseline pass over ntedvs.com highlighting layout overlap, color contrast, and accessibility gaps.",
            "next_prompt": "Re-run the site after applying layout, contrast, and aria-label fixes.",
        },
        "artifacts": [
            {"type": "screenshot", "path": f"runs/{run_id}/artifacts/issue-hero-overlap.png"},
            {"type": "screenshot", "path": f"runs/{run_id}/artifacts/issue-footer-contrast.png"},
            {"type": "screenshot", "path": f"runs/{run_id}/artifacts/issue-nav-toggle.png"},
            {"type": "json", "path": f"runs/{run_id}/artifacts/action_log.json"},
            {"type": "markdown", "path": f"runs/{run_id}/summary.md"},
        ],
        "notes": [
            "Mock run generated locally; replace artifacts with real ntedvs.com captures for live demos.",
            f"Instruction captured: {instruction}",
            "Next prompt: Implement the recommended fixes and capture a follow-up run.",
        ],
    }
    return payload


def _produce_run_payload(
    *,
    instruction: str,
    mode: str,
    host: str,
    poll_interval: float,
    max_polls: int,
) -> Tuple[dict, str]:
    if mode == "live":
        try:
            payload = _trigger_live_run(
                instruction,
                host=host,
                poll_interval=poll_interval,
                max_polls=max_polls,
            )
            return payload, "live"
        except Exception as exc:  # pylint: disable=broad-exception-caught
            sys.stderr.write(
                f"[warn] Live orchestration failed ({exc!r}); falling back to mock run.\n"
            )
    payload = _build_mock_run(instruction)
    return payload, "mock"


# ---------------------------------------------------------------------------
# Persistence + reporting
# ---------------------------------------------------------------------------


def _write_placeholder_artifacts(run_dir: Path, payload: dict) -> None:
    artifacts_dir = run_dir / "artifacts"
    _ensure_dir(artifacts_dir)

    placeholders = {
        "issue-hero-overlap.png": (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
            "/w8AAwMCAO3X5bUAAAAASUVORK5CYII="
        ),
        "issue-footer-contrast.png": (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mMoAwADWgFfXxsTlgAAAABJRU5ErkJggg=="
        ),
        "issue-nav-toggle.png": (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
            "Pw8AAwMCAO3X5bUAAAAASUVORK5CYII="
        ),
    }
    for filename, encoded in placeholders.items():
        target = artifacts_dir / filename
        if not target.exists():
            target.write_bytes(base64.b64decode(encoded))

    action_log_path = artifacts_dir / "action_log.json"
    if not action_log_path.exists():
        action_log = {
            "steps": [
                {"action": "navigate", "target": "http://localhost:4173/"},
                {"action": "hover", "target": "[data-testid=\"hero-cta\"]"},
                {
                    "action": "collect-styles",
                    "target": "[data-testid=\"hero-cta\"]",
                    "computed": {"color": "rgb(59, 130, 246)", "transitionTimingFunction": "linear"},
                },
            ],
            "notes": payload.get("notes", []),
        }
        action_log_path.write_text(json.dumps(action_log, indent=2), encoding="utf-8")


def _render_observations_table(observations: List[Observation]) -> str:
    if not observations:
        return "_No observations recorded._"
    rows = [
        [
            obs.selector or "—",
            obs.severity.title(),
            obs.message + (f" - {obs.description}" if obs.description else ""),
            obs.suggested_prompt or "—",
        ]
        for obs in observations
    ]
    table = _build_markdown_table(
        ["Selector", "Severity", "Message", "Suggested Prompt"],
        rows,
    )
    return table or "_No observations recorded._"


def _render_errors_table(errors: List[RunError]) -> str:
    if not errors:
        return "_No errors reported._"
    rows = [
        [
            err.code or "—",
            err.message,
        ]
        for err in errors
    ]
    table = _build_markdown_table(["Code", "Message"], rows)
    return table or "_No errors reported._"


def _compose_summary_markdown(payload: dict, observations: List[Observation], errors: List[RunError]) -> str:
    result = payload.get("result", {})
    highlights = result.get("highlights", [])
    notes = payload.get("notes", [])
    instruction = payload.get("instruction") or result.get("instruction")
    next_prompt = payload.get("next_prompt") or result.get("next_prompt")
    description = payload.get("description") or result.get("description")
    lines = [
        f"# Run {payload.get('run_id', 'unknown')}",
        "",
        f"- Status: {result.get('status', 'unknown')}",
        f"- Started at: {result.get('started_at', 'n/a')}",
        f"- Finished at: {result.get('finished_at', 'n/a')}",
        f"- Duration: {result.get('duration_ms', 0)} ms",
        "",
    ]
    if instruction:
        lines.extend(["## Instruction", instruction, ""])
    if next_prompt:
        lines.extend(["## Next Prompt", next_prompt, ""])
    if description:
        lines.extend(["## Description", description, ""])
    if highlights:
        lines.extend(["## Highlights", *(f"- {item}" for item in highlights), ""])
    lines.extend(["## Observations", _render_observations_table(observations), ""])
    lines.extend(["## Errors", _render_errors_table(errors), ""])
    if notes:
        lines.extend(["", "## Notes", *(f"- {note}" for note in notes)])
    return "\n".join(lines).strip() + "\n"


def _persist_run_payload(payload: dict) -> Tuple[Path, List[Observation], List[RunError]]:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = payload.get("run_id", f"run-{uuid.uuid4()}")
    run_dir = RUNS_DIR / run_id
    _ensure_dir(run_dir)

    observations = [Observation.from_dict(item) for item in payload.get("result", {}).get("observations", [])]
    errors = [RunError.from_dict(item) for item in payload.get("result", {}).get("errors", [])]

    payload.setdefault("artifacts", [])
    payload.setdefault("notes", [])
    payload.setdefault("request", {})
    payload.setdefault("result", {})

    result = payload["result"]
    result.setdefault("status", "unknown")
    result.setdefault("exit_code", -1)
    result.setdefault("duration_ms", 0)
    result.setdefault("started_at", _now().isoformat())
    result.setdefault("finished_at", result["started_at"])
    result.setdefault("highlights", [])
    result.setdefault("observations", [])
    result.setdefault("errors", [])
    if "description" not in result and payload.get("description") is not None:
        result["description"] = payload["description"]
    if "next_prompt" not in result and payload.get("next_prompt") is not None:
        result["next_prompt"] = payload["next_prompt"]

    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    summary_path = run_dir / "summary.md"
    summary_path.write_text(_compose_summary_markdown(payload, observations, errors), encoding="utf-8")

    _write_placeholder_artifacts(run_dir, payload)
    return run_dir, observations, errors


def _write_global_reports() -> Tuple[Path | None, Path | None]:
    summaries = load_runs(RUNS_DIR)
    if not summaries:
        return None, None
    artifacts = generate_report(summaries)
    overview_path = RUNS_DIR / "overview.md"
    overview_path.write_text(artifacts.table_markdown + "\n", encoding="utf-8")
    gallery_path = RUNS_DIR / "gallery.html"
    gallery_path.write_text(artifacts.gallery_html, encoding="utf-8")
    return overview_path, gallery_path


def _print_run_summary(
    *,
    payload: dict,
    run_dir: Path,
    observations: List[Observation],
    errors: List[RunError],
    mode_used: str,
    overview_path: Path | None,
    gallery_path: Path | None,
) -> None:
    rel_dir = run_dir.relative_to(ROOT)
    print(f"\nRun `{payload.get('run_id')}` stored in `{rel_dir}` (mode: {mode_used}).")
    print("Observations:")
    print(_render_observations_table(observations))
    print("\nErrors:")
    print(_render_errors_table(errors))
    print(
        f"\nAggregate overview saved to `{(overview_path or (RUNS_DIR / 'overview.md')).relative_to(ROOT)}` "
        f"and gallery to `{(gallery_path or (RUNS_DIR / 'gallery.html')).relative_to(ROOT)}`."
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def handle_run(ns: argparse.Namespace) -> None:
    payload, mode_used = _produce_run_payload(
        instruction=ns.instruction,
        mode=ns.mode,
        host=ns.host,
        poll_interval=ns.poll_interval,
        max_polls=ns.max_polls,
    )
    run_dir, observations, errors = _persist_run_payload(payload)
    overview_path, gallery_path = _write_global_reports()
    _print_run_summary(
        payload=payload,
        run_dir=run_dir,
        observations=observations,
        errors=errors,
        mode_used=mode_used,
        overview_path=overview_path,
        gallery_path=gallery_path,
    )
    if gallery_path:
        _open_gallery_in_browser(gallery_path, getattr(ns, "open_browser", True))


def handle_demo(ns: argparse.Namespace) -> None:
    instruction = ns.instruction or "Fix the hover animation on the hero CTA to use brand.primary."
    args = argparse.Namespace(
        instruction=instruction,
        mode="mock",
        host=DEFAULT_HOST,
        poll_interval=ns.poll_interval,
        max_polls=ns.max_polls,
        open_browser=ns.open_browser,
    )
    handle_run(args)


def handle_report(ns: argparse.Namespace) -> None:
    summaries = load_runs(RUNS_DIR)
    if not summaries:
        sys.stderr.write("No runs found in `runs/`. Execute `python tool.py run --instruction \"...\"` first.\n")
        sys.exit(1)
    artifacts = generate_report(summaries)
    overview_path = RUNS_DIR / "overview.md"
    overview_path.write_text(artifacts.table_markdown + "\n", encoding="utf-8")
    gallery_path = RUNS_DIR / "gallery.html"
    gallery_path.write_text(artifacts.gallery_html, encoding="utf-8")
    print(artifacts.table_markdown)
    print(f"\nOverview stored at `{overview_path}`; gallery at `{gallery_path}`.")
    _open_gallery_in_browser(gallery_path, ns.open_browser)


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CodeUse reporter CLI (Person D).")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Execute an instruction via orchestrator (or local mock).")
    run_parser.add_argument("--instruction", required=True, help="Natural-language task instruction for the orchestrator.")
    run_parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default="mock",
        help="mock (default) fakes executor output; live calls the orchestrator API.",
    )
    run_parser.add_argument("--host", default=DEFAULT_HOST, help="Base URL for the orchestrator service.")
    run_parser.add_argument("--poll-interval", type=float, default=2.0, help="Seconds between polling orchestrator status.")
    run_parser.add_argument("--max-polls", type=int, default=30, help="Maximum polling attempts before timing out.")
    run_parser.set_defaults(open_browser=True)
    run_parser.add_argument(
        "--no-open-browser",
        dest="open_browser",
        action="store_false",
        help="Skip automatically opening the gallery in a browser window.",
    )

    demo_parser = subparsers.add_parser("demo", help="Shortcut for a canned mock run used in presentations.")
    demo_parser.add_argument("--instruction", help="Optional override instruction for the demo flow.")
    demo_parser.add_argument("--poll-interval", type=float, default=2.0)
    demo_parser.add_argument("--max-polls", type=int, default=30)
    demo_parser.set_defaults(open_browser=True)
    demo_parser.add_argument(
        "--no-open-browser",
        dest="open_browser",
        action="store_false",
        help="Skip automatically opening the gallery in a browser window.",
    )

    report_parser = subparsers.add_parser("report", help="Render a consolidated report of all stored runs.")
    report_parser.set_defaults(open_browser=True)
    report_parser.add_argument(
        "--no-open-browser",
        dest="open_browser",
        action="store_false",
        help="Skip automatically opening the gallery in a browser window.",
    )

    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    ns = parse_args(argv or sys.argv[1:])
    if ns.command == "run":
        handle_run(ns)
    elif ns.command == "demo":
        handle_demo(ns)
    elif ns.command == "report":
        handle_report(ns)
    else:
        print("Usage: python tool.py [run|demo|report] ...", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
