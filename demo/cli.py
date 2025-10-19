"""Command-line demo frontend for the CodeUse pipeline."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from tool.executor.executor import run_audit
from tool.pipeline.bridge import process_executor_result


load_dotenv()


def _load_prompt(path: Optional[str]) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    if not path:
        return None, None
    prompt_path = pathlib.Path(path)
    data = json.loads(prompt_path.read_text(encoding="utf-8"))
    title = data.get("title") or data.get("task") or "Gemini CU Task"
    return title, data


def _write_ui_json(result_json_path: str, ui_payload: Dict[str, Any]) -> str:
    ui_path = pathlib.Path(result_json_path).with_name("ui.json")
    ui_path.write_text(json.dumps(ui_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(ui_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CodeUse demo pipeline")
    parser.add_argument("--url", help="Target page to audit")
    parser.add_argument("--executor-json", help="Path to a saved executor blob")
    parser.add_argument("--prompt-file", help="Gemini CU-style TaskSpec for narration")
    parser.add_argument(
        "--slow-ms",
        type=int,
        default=int(os.getenv("DEMO_SLOW_MS", "0")),
        help="Slow motion in milliseconds for Playwright actions",
    )
    args = parser.parse_args()

    if not args.url and not args.executor_json:
        print("Provide --url or --executor-json")
        return 2

    title, prompt = _load_prompt(args.prompt_file)
    if prompt:
        print("\n=== GEMINI CU PROMPT (for narration) ===")
        print(json.dumps(prompt, indent=2, ensure_ascii=False))
        print()

    if args.executor_json:
        raw = json.loads(pathlib.Path(args.executor_json).read_text(encoding="utf-8"))
    else:
        if not args.url:
            print("--url is required when not using --executor-json")
            return 2
        print(f"Running executor against {args.url} (slow_ms={args.slow_ms}) ...")
        raw = run_audit(target_url=args.url, run_id=None, slow_ms=max(args.slow_ms, 0))

    bridge_out = process_executor_result(raw, user_prompt=title)
    ui_path = _write_ui_json(bridge_out.result_json_path, bridge_out.ui_payload)

    issues = bridge_out.audit.issues or []
    issue_counts: Dict[str, int] = {}
    for issue in issues:
        issue_counts[issue.type] = issue_counts.get(issue.type, 0) + 1

    cta_selector = (
        bridge_out.audit.primary_cta.selector
        if bridge_out.audit.primary_cta is not None
        else "None"
    )

    print("\n=== DEMO SUMMARY ===")
    print("Run ID:       ", bridge_out.run_id)
    print("Result JSON:  ", bridge_out.result_json_path)
    print("UI JSON:      ", ui_path)
    print("Target URL:   ", bridge_out.audit.target_url)
    print("CTA:          ", cta_selector)
    print("Success:      ", bridge_out.audit.success)
    print("Issue types:  ", issue_counts or {})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

