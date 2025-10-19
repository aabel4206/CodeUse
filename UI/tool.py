"""
Interactive CodeUse CLI.

This module provides a user-facing interface that mirrors the demo runner
but calls the orchestrator loop directly. It supports an interactive menu
for repeated audits and a non-interactive single-run mode.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Ensure the repository root is on sys.path when the script is executed from UI/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tool.orchestrator.loop import run_task

DEFAULT_URL = "http://localhost:5173/index.html"
DEFAULT_SELECTOR = "#btn1"
DEFAULT_MODE = "auto"
DEFAULT_EXECUTOR_URL = "http://127.0.0.1:8000"
MODES: Tuple[str, ...] = ("auto", "hover", "click", "screenshot")
PLAN_CHOICES: Tuple[str, ...] = ("none", "hover", "click", "screenshot")


class _PlannedModels:
    def __init__(self, function_names: List[str]):
        self._function_names = function_names

    def generate_content(self, *args: Any, **kwargs: Any) -> Dict[str, object]:
        parts = [{"function_call": {"name": name}} for name in self._function_names]
        return {"candidates": [{"content": {"parts": parts}}]}


class CLIGeminiClient:
    def __init__(self, function_names: List[str]):
        self.models = _PlannedModels(function_names)


def _prompt_str(message: str, default: Optional[str] = None, *, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{message}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print("This field is required.")


def _prompt_choice(message: str, choices: Sequence[str], default: str) -> str:
    normalized = {choice.lower(): choice for choice in choices}
    prompt = f"{message} ({' | '.join(choices)})"
    while True:
        value = _prompt_str(prompt, default).strip().lower()
        if value in normalized:
            return normalized[value]
        print(f"Invalid choice '{value}'. Expected one of: {', '.join(choices)}.")


def _prompt_yes_no(message: str, default: bool = False) -> bool:
    default_str = "y" if default else "n"
    prompt = f"{message} (y/N)" if not default else f"{message} (Y/n)"
    while True:
        value = _prompt_str(prompt, default_str).strip().lower()
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Please answer y or n.")


def _infer_mode(instruction: str) -> str:
    text = instruction.lower()
    if "click" in text:
        return "click"
    if "screenshot" in text:
        return "screenshot"
    if "hover" in text:
        return "hover"
    return "hover"


def _functions_for_mode(mode: str) -> List[str]:
    if mode == "hover":
        return ["hover", "measure_hover_metrics", "screenshot"]
    if mode == "click":
        return ["click", "screenshot"]
    if mode == "screenshot":
        return ["screenshot"]
    return ["hover", "screenshot"]


def _simulate_dry_run(url: str, selector: str) -> Dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"dryrun-{timestamp}"
    return {
        "success": True,
        "run_id": run_id,
        "audit": {
            "run_id": run_id,
            "target_url": url,
            "issues": [
                {
                    "severity": "warning",
                    "type": "layout",
                    "summary": "Simulated overlap of CTA and heading (dry-run).",
                    "selector": selector,
                },
                {
                    "severity": "info",
                    "type": "contrast",
                    "summary": "Simulated low contrast on footer link (dry-run).",
                    "selector": "footer a[href*='contact']",
                },
            ],
            "artifacts": {"screenshot": "simulated_screenshot.png"},
            "summary": "2 simulated issues generated in dry-run mode.",
        },
    }


def _build_gemini_client(plan: Optional[str], effective_mode: str, instruction: str) -> Tuple[CLIGeminiClient, str]:
    if plan:
        return CLIGeminiClient(_functions_for_mode(plan)), f"stub:{plan}"
    fallback = effective_mode if effective_mode in ("hover", "click", "screenshot") else _infer_mode(instruction)
    return CLIGeminiClient(_functions_for_mode(fallback)), f"stub:{fallback}"


def _run_async(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "asyncio.run()" in str(exc):
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        raise


def _print_audit(result: Dict[str, Any]) -> None:
    print("\n=== Audit Result ===")
    run_id = result.get("run_id") or "n/a"
    print(f"Run ID: {run_id}")

    audit = result.get("audit") or {}
    target_url = audit.get("target_url") or result.get("summary", {}).get("final_url") or "n/a"
    print(f"Target URL: {target_url}")

    summary_text: Optional[str] = None
    if isinstance(audit.get("summary"), str) and audit["summary"].strip():
        summary_text = audit["summary"].strip()
    elif isinstance(result.get("summary"), dict):
        summary_dict = result["summary"]
        summary_text = summary_dict.get("description")
        if not summary_text and summary_dict.get("target_met") is not None:
            summary_text = f"Target met: {summary_dict.get('target_met')}"
    if summary_text:
        print(f"Summary: {summary_text}")

    if not result.get("success", False):
        print("\nRun failed.")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    issues = audit.get("issues") or []
    if issues:
        print(f"\nIssues ({len(issues)}):")
        for issue in issues:
            severity = (issue.get("severity") or "unknown").lower()
            issue_type = issue.get("type") or "issue"
            summary_line = issue.get("summary") or ""
            selector = issue.get("selector")
            selector_part = f" (selector: {selector})" if selector else ""
            print(f"  - [{severity}] {issue_type}: {summary_line}{selector_part}")
    else:
        print("\nNo issues detected 🎉")

    artifacts = audit.get("artifacts") or result.get("artifacts") or {}
    if artifacts:
        print("\nArtifacts:")
        if isinstance(artifacts, dict):
            for key, value in artifacts.items():
                if isinstance(value, (list, tuple)):
                    for item in value:
                        print(f"  - {key}: {item}")
                else:
                    print(f"  - {key}: {value}")
        else:
            print(f"  - {artifacts}")


def _run_once(
    url: str,
    selector: str,
    instruction: str,
    mode: str,
    executor_url: str,
    plan: str,
    *,
    dry_run: bool,
) -> bool:
    instruction = instruction.strip()
    if dry_run:
        print("\n[Dry-run mode] Using simulated audit data. No backend or Playwright required.")
        result = _simulate_dry_run(url, selector)
        _print_audit(result)
        return True

    requested_mode = mode.lower()
    effective_mode = requested_mode if requested_mode != "auto" else _infer_mode(instruction)
    plan_name = plan.lower()
    plan_name = None if plan_name in ("", "none") else plan_name

    client, planning_strategy = _build_gemini_client(plan_name, effective_mode, instruction)
    spec = {
        "target_url": url,
        "target_selector": selector,
        "instruction": instruction,
    }

    print("\nRunning audit...")
    print(f"Executor: {executor_url}")
    print(f"Mode: {effective_mode} | Planning: {planning_strategy}")

    try:
        result = _run_async(run_task(spec, client, executor_url))
    except Exception as exc:
        print(f"\nError while executing run: {exc}")
        return False

    _print_audit(result)
    return True


def _interactive_audit() -> None:
    url = _prompt_str("Target URL", DEFAULT_URL)
    selector = _prompt_str("Target CSS selector", DEFAULT_SELECTOR)
    instruction = _prompt_str("Instruction", required=True)
    mode = _prompt_choice("Action mode", MODES, DEFAULT_MODE)
    executor_url = _prompt_str("Executor URL", DEFAULT_EXECUTOR_URL)
    plan_choice = _prompt_choice("Optional deterministic plan", PLAN_CHOICES, "none")
    dry_run = _prompt_yes_no("Run in dry-run mode?", False)

    _run_once(url, selector, instruction, mode, executor_url, plan_choice, dry_run=dry_run)

    while True:
        answer = input("Re-run with changes? (y/N): ").strip().lower()
        if answer != "y":
            break
        print(
            f"(Keeping URL={url}, mode={mode}, executor={executor_url}, plan={plan_choice}, dry_run={dry_run})"
        )
        instruction = _prompt_str("Instruction", instruction, required=True)
        selector = _prompt_str("Target CSS selector", selector)
        _run_once(url, selector, instruction, mode, executor_url, plan_choice, dry_run=dry_run)


def _interactive_menu() -> None:
    while True:
        print("\nCodeUse Interactive CLI")
        print("1) New audit")
        print("2) Quit")
        choice = input("Select option: ").strip()
        if choice == "1":
            _interactive_audit()
        elif choice in {"2", "q", "quit"}:
            print("Goodbye!")
            return
        else:
            print("Invalid selection. Please choose 1 or 2.")


def _non_interactive(args: argparse.Namespace) -> None:
    instruction = args.instruction.strip() if args.instruction else ""
    if not instruction:
        print("--instruction is required when using --non-interactive.", file=sys.stderr)
        sys.exit(2)
    success = _run_once(
        args.url,
        args.selector,
        instruction,
        args.mode,
        args.executor_url,
        args.plan,
        dry_run=args.dry_run,
    )
    if not success:
        sys.exit(1)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CodeUse interactive CLI.")
    parser.add_argument("--non-interactive", action="store_true", help="Run a single audit and exit.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Target URL for the audit.")
    parser.add_argument("--selector", default=DEFAULT_SELECTOR, help="CSS selector to investigate.")
    parser.add_argument("--instruction", help="Instruction describing the audit goal.")
    parser.add_argument("--mode", choices=MODES, default=DEFAULT_MODE, help="Action mode preset.")
    parser.add_argument("--executor-url", default=DEFAULT_EXECUTOR_URL, help="Executor service URL.")
    parser.add_argument("--plan", choices=PLAN_CHOICES, default="none", help="Deterministic planning preset.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use simulated results without contacting the backend.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parse_args(argv)
    if args.non_interactive:
        _non_interactive(args)
    else:
        _interactive_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
