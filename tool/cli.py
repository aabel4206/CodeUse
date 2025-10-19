"""Command-line interface for running the orchestrator against the local executor."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Dict, List

from tool.orchestrator.loop import run_task


class _PlannedModels:
    """Minimal Gemini stub that emits pre-selected function calls."""

    def __init__(self, function_names: List[str]):
        self._function_names = function_names

    def generate_content(self, *args, **kwargs) -> Dict[str, object]:
        parts = [{"function_call": {"name": name}} for name in self._function_names]
        return {"candidates": [{"content": {"parts": parts}}]}


class CLIGeminiClient:
    """Shim that mimics the Gemini client structure expected by run_task."""

    def __init__(self, function_names: List[str]):
        self.models = _PlannedModels(function_names)


def _infer_mode(instruction: str) -> str:
    text = instruction.lower()
    if "hover" in text:
        return "hover"
    if "click" in text:
        return "click"
    return "screenshot"


def _functions_for_mode(mode: str) -> List[str]:
    if mode == "hover":
        return ["hover_primary_button", "capture_hover_screenshot"]
    if mode == "click":
        return ["click_primary_button", "take_screenshot"]
    return ["capture_page_screenshot"]


def _print_audit(audit: Dict[str, object]) -> None:
    print("\n=== Audit Result ===")
    print(f"Run ID: {audit.get('run_id')}")
    print(f"Target URL: {audit.get('target_url')}")
    summary = audit.get("summary")
    if summary:
        print(summary)

    issues = audit.get("issues") or []
    if not issues:
        print("No issues detected 🎉")
    else:
        print(f"{len(issues)} issue(s) detected:")
        for issue in issues:
            print(
                f" - [{issue.get('severity')}] {issue.get('type')}: {issue.get('summary')}"
            )
    artifacts = audit.get("artifacts") or {}
    if artifacts:
        print("\nArtifacts:")
        for key, value in artifacts.items():
            print(f" - {key}: {value}")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the orchestrator pipeline against the local executor."
    )
    parser.add_argument(
        "instruction",
        nargs="?",
        help="Prompt describing what to verify (defaults to interactive input).",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:5173/index.html",
        help="Target page URL to load (default: %(default)s)",
    )
    parser.add_argument(
        "--selector",
        default="#btn1",
        help="Target CSS selector (default: %(default)s)",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "hover", "click", "screenshot"],
        default="auto",
        help="Action plan preset (default: %(default)s)",
    )

    args = parser.parse_args(argv)

    instruction = args.instruction or input("Instruction> ").strip()
    if not instruction:
        print("No instruction provided. Aborting.", file=sys.stderr)
        return 1

    mode = args.mode
    if mode == "auto":
        mode = _infer_mode(instruction)

    function_names = _functions_for_mode(mode)

    gemini_client = CLIGeminiClient(function_names)
    spec = {
        "target_url": args.url,
        "target_selector": args.selector,
        "instruction": instruction,
    }

    try:
        result = asyncio.run(run_task(spec, gemini_client))
    except Exception as exc:  # pragma: no cover - surfaced to the user
        print(f"Failed to run task: {exc}", file=sys.stderr)
        return 1

    if not result.get("success"):
        print("Run failed.")
        print(json.dumps(result, indent=2))
        return 1

    audit = result.get("audit")
    if audit:
        _print_audit(audit)
    else:
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
