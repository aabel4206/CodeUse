"""Command-line demo frontend for the CodeUse pipeline."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from tool.pipeline.bridge import process_executor_result


load_dotenv()


def _load_prompt(path: Optional[str]) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    if not path:
        return None, None
    prompt_path = pathlib.Path(path)
    data = json.loads(prompt_path.read_text(encoding="utf-8"))
    title = data.get("title") or data.get("task") or "Gemini CU Task"
    return title, data


def _replace_url_tokens(raw_url: Optional[str], target_url: Optional[str]) -> Optional[str]:
    if not raw_url:
        return target_url
    if "<URL>" in raw_url:
        if target_url:
            return raw_url.replace("<URL>", target_url)
        return None
    return raw_url


def _infer_selector(prompt: Optional[Dict[str, Any]], fallback: str = "#btn1") -> str:
    if not prompt:
        return fallback
    candidate = prompt.get("target_selector")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    for step in prompt.get("steps", []) or []:
        selector = step.get("selector")
        if isinstance(selector, str) and selector.strip():
            return selector.strip()
    return fallback


def _build_exec_payload(
    prompt: Optional[Dict[str, Any]],
    target_url: Optional[str],
    slow_ms: int,
) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = list((prompt or {}).get("steps", []) or [])
    actions: List[Dict[str, Any]] = []
    selector = (prompt or {}).get("target_selector")
    selector = selector if isinstance(selector, str) and selector.strip() else None
    measure_hover = False
    effective_url = target_url
    initial_url_set = False

    for idx, step in enumerate(steps):
        action_name = (step.get("action") or "").strip().lower()
        if not action_name:
            continue

        if action_name == "go_to":
            resolved = _replace_url_tokens(step.get("url"), target_url)
            if resolved:
                if not initial_url_set:
                    effective_url = resolved
                    initial_url_set = True
                else:
                    actions.append({"fn": "navigate", "args": {"url": resolved}})
        elif action_name == "hover":
            sel = step.get("selector") or selector
            if isinstance(sel, str) and sel.strip():
                selector = sel.strip()
                actions.append({"fn": "hover", "args": {"selector": selector}})
            measure_hover = True
        elif action_name == "scan_links":
            actions.append({"fn": "scan_links", "args": {}})
        elif action_name == "scan_images":
            actions.append({"fn": "scan_images", "args": {}})
        elif action_name == "measure_target":
            sel = step.get("selector")
            if isinstance(sel, str) and sel.strip():
                actions.append({"fn": "measure_target", "args": {"selector": sel.strip()}})
        elif action_name == "detect_overlap":
            sel = step.get("selector")
            if isinstance(sel, str) and sel.strip():
                actions.append({"fn": "detect_overlap", "args": {"selector": sel.strip()}})
        elif action_name == "read_computed_style":
            sel = step.get("selector")
            if isinstance(sel, str) and sel.strip():
                args = {"selector": sel.strip()}
                pseudo = step.get("pseudo")
                if isinstance(pseudo, str) and pseudo.strip():
                    args["pseudo"] = pseudo.strip()
                actions.append({"fn": "get_computed_style", "args": args})
        elif action_name == "screenshot":
            label = step.get("label") or f"step-{idx + 1}-screenshot"
            actions.append({"fn": "screenshot", "args": {"label": label}})
        elif action_name == "click":
            sel = step.get("selector")
            if isinstance(sel, str) and sel.strip():
                actions.append({"fn": "click", "args": {"selector": sel.strip()}})
        elif action_name == "assert_text":
            sel = step.get("selector")
            contains = step.get("contains") or step.get("text")
            if (
                isinstance(sel, str)
                and sel.strip()
                and isinstance(contains, str)
                and contains.strip()
            ):
                actions.append(
                    {
                        "fn": "assert_text",
                        "args": {"selector": sel.strip(), "contains": contains.strip()},
                    }
                )
        elif action_name == "check_link":
            sel = step.get("selector")
            if isinstance(sel, str) and sel.strip():
                payload = {"selector": sel.strip()}
                label = step.get("label")
                if isinstance(label, str) and label.strip():
                    payload["label"] = label.strip()
                actions.append({"fn": "check_link", "args": payload})
        elif action_name == "check_disabled":
            sel = step.get("selector")
            if isinstance(sel, str) and sel.strip():
                actions.append({"fn": "check_disabled", "args": {"selector": sel.strip()}})
        elif action_name == "read_text":
            sel = step.get("selector")
            if isinstance(sel, str) and sel.strip():
                actions.append({"fn": "get_text", "args": {"selector": sel.strip()}})
        elif action_name == "count_elements":
            sel = step.get("selector")
            if isinstance(sel, str) and sel.strip():
                actions.append({"fn": "count_elements", "args": {"selector": sel.strip()}})

    selector = selector or _infer_selector(prompt)
    if not measure_hover and selector:
        measure_hover = True

    if not actions:
        selector = selector or "#btn1"
        actions = [
            {"fn": "hover", "args": {"selector": selector}},
            {"fn": "scan_links", "args": {}},
            {"fn": "scan_images", "args": {}},
            {"fn": "measure_target", "args": {"selector": ".tiny-btn"}},
            {"fn": "detect_overlap", "args": {"selector": selector}},
        ]
        measure_hover = True

    payload = {
        "url": effective_url or target_url,
        "actions": actions,
        "selector": selector or "#btn1",
        "step": 1,
        "measure_hover": bool(measure_hover),
        "slow_ms": max(int(slow_ms or 0), 0),
    }
    return payload


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

        exec_payload = _build_exec_payload(prompt, args.url, args.slow_ms)
        if not exec_payload.get("url"):
            print("Unable to determine target URL for executor request.")
            return 2

        base_url = (os.getenv("EXECUTOR_BASE_URL") or "http://localhost:8001").rstrip("/")
        endpoint = f"{base_url}/execute"
        print(f"Calling executor at {endpoint} ...")

        try:
            response = httpx.post(endpoint, json=exec_payload, timeout=httpx.Timeout(60.0))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"Executor request failed: {exc}")
            resp = getattr(exc, "response", None)
            if resp is not None:
                try:
                    print(resp.text)
                except Exception:
                    pass
            return 1
        except Exception as exc:
            print(f"Executor request failed: {exc}")
            return 1

        raw = response.json()

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

    # Display improvement prompts if available
    if issues:
        print("\n=== IMPROVEMENT PROMPTS ===")
        for i, issue in enumerate(issues, 1):
            print(f"\n{i}. {issue.type.replace('_', ' ').title()}")
            print(f"   Issue: {issue.summary}")
            if hasattr(issue, 'improvement_prompt') and issue.improvement_prompt:
                print(f"   Prompt: {issue.improvement_prompt}")
            else:
                print("   Prompt: [No improvement prompt generated]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
