"""Main orchestration loop for the CodeUse tool."""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:  # Load environment variables from .env when available
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from .state import save_observation, save_result, update_status
from tool.orchestrator.state import ProbeEvent

# Normalization, aggregation, and persistence helpers
from tool.orchestrator.adapter import normalize_with_openrouter
from tool.reporter.aggregator import build_audit_result
from tool.reporter.reporter import write_result_json

from .prompts.system_prompts import SYSTEM_PROMPT  # optional; can be blank


# -----------------------
# Public entrypoint
# -----------------------
async def run_task(
    task_spec: Dict[str, Any],
    gemini_client,                      # from main.py (google.genai.Client)
    executor_base_url: str,             # e.g. "http://localhost:8001"
    *, excluded_functions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Single-iteration run:
      1) Ask Gemini Computer Use for an action plan (browser env).
      2) Translate to a Playwright action list we support.
      3) POST to executor /execute with ExecRequest.
      4) Save observation + result and return RunResult JSON.
    """
    run_id = str(uuid.uuid4())
    run_dir = Path(f"tool/runs/{run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)

    # Status boot
    update_status(run_dir, {"state": "running", "step": 0, "success": None})

    # -----------------------
    # 1) Build CU request
    # -----------------------
    contents = _build_gemini_contents(task_spec)
    generate_content_config = _build_gemini_config(excluded_functions or ["drag_and_drop"])

    # -----------------------
    # 2) Call Gemini CU (one turn)
    # -----------------------
    cu_raw = None
    try:
        cu_raw = gemini_client.models.generate_content(
            model="gemini-2.5-computer-use-preview-10-2025",
            contents=contents,
            config=generate_content_config,
        )
    except Exception as e:
        # Hard fail on CU errors (executor retry won’t help)
        result = _finalize_failure(
            run_dir,
            run_id,
            errors=[f"cu_error.gemini_request_failed: {e}"],
            observations=[]
        )
        return result

    # Persist CU raw for debugging
    _save_json(run_dir / "cu_response.json", _safe_jsonify(cu_raw))

    # -----------------------
    # 3) Translate CU → Playwright actions (limited, selector-based)
    # -----------------------
    actions = _cu_to_playwright_actions(task_spec, cu_raw, run_id)

    # Guard: must have at least one action for error checking
    if not actions:
        # Default error checking actions
        actions = _default_error_check_actions(task_spec, run_id)

    # Build ExecRequest payload
    exec_payload = {
        "url": task_spec.get("target_url") or "https://example.com",  # Ensure valid URL
        "actions": actions,
        "selector": task_spec.get("target_selector", "body"),
        "step": 1,
        "measure_hover": False,  # Not needed for error checking
    }

    # -----------------------
    # 4) Call executor /execute with up to 2 retries on failure
    # -----------------------
    exec_result: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    for attempt in range(1, 3):  # attempt 1 and 2
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{executor_base_url}/execute", json=exec_payload)
                resp.raise_for_status()
                exec_result = resp.json()
                break
        except Exception as e:
            errors.append(f"executor_error.attempt_{attempt}: {e}")
            await asyncio.sleep(0.35)

    observation_payload: Dict[str, Any] = {}
    executor_results: List[Dict[str, Any]] = []
    executor_errors: List[str] = []
    executor_ok = False

    if isinstance(exec_result, dict):
        observation_payload = exec_result.get("observation") or {}
        if isinstance(observation_payload, dict):
            executor_errors = list(observation_payload.get("errors") or [])
        raw_results = exec_result.get("results") or []
        if isinstance(raw_results, list):
            executor_results = [r for r in raw_results if isinstance(r, dict)]
        executor_ok = (
            bool(exec_result)
            and not executor_errors
            and all(bool(r.get("ok", True)) for r in executor_results)
        )

    # Record observation (even on failure we store what we tried)
    observation = {
        "step": 1,
        "actions": actions,
        "exec_payload": exec_payload,
        "executor_result": exec_result,
        "executor_ok": executor_ok,
        "errors": errors,
        "timestamp": time.time(),
    }
    save_observation(run_dir, 1, observation)

    # -----------------------
    # 5) Finalize
    # -----------------------
    if not executor_ok:
        errors.extend(executor_errors)
        result = _finalize_failure(run_dir, run_id, errors=errors, observations=[observation])
        return result

    primary_cta, probe_event_dict = normalize_with_openrouter(exec_result)
    probe_events: List[ProbeEvent] = []
    if probe_event_dict:
        try:
            probe_events.append(ProbeEvent.model_validate(probe_event_dict))
        except Exception:
            pass

    artifacts = {
        "screenshots": observation_payload.get("screenshots"),
        "screenshot": observation_payload.get("screenshot"),
        "executor_run_id": exec_result.get("run_id"),
        "results": executor_results,
        "observation": observation_payload,
        "action_log": str(run_dir / "step-1.json"),
    }

    audit = build_audit_result(
        run_id=run_id,
        target_url=exec_payload["url"],
        primary_cta=primary_cta,
        probe_events=probe_events,
        console_lines=observation_payload.get("console", []) or [],
        link_probes=observation_payload.get("link_probes", []) or [],
        dom_scan=observation_payload.get("dom_scan"),
        artifacts=artifacts,
    )
    audit_path = write_result_json(str(run_dir), audit)

    final_url = observation_payload.get("url") or exec_payload["url"]
    orchestrator_result = {
        "run_id": run_id,
        "success": True,
        "summary": {
            "target_met": True,          # executor judged it; we accept for MVP
            "steps_used": 1,
            "final_url": final_url,
            "selector": task_spec.get("target_selector"),
        },
        "observations": [observation],
        "errors": [],
        "artifacts": {
            "screenshots_dir": str(run_dir),
            "action_log": str(run_dir / "step-1.json"),
            "audit_path": audit_path,
        },
        "audit": audit.model_dump(),
    }
    summary_path = run_dir / "orchestrator_result.json"
    _save_json(summary_path, orchestrator_result)
    update_status(run_dir, {"state": "done", "step": 1, "success": True})
    return orchestrator_result


# -----------------------
# Helpers
# -----------------------
def _build_gemini_config(excluded: List[str]):
    # Mirrors the exact structure you provided (browser env + optional excludes)
    from google import genai
    return genai.types.GenerateContentConfig(
        tools=[
            genai.types.Tool(
                computer_use=genai.types.ComputerUse(
                    environment=genai.types.Environment.ENVIRONMENT_BROWSER,
                    excluded_predefined_functions=excluded
                )
            ),
            # Optional: Inject custom tool declarations later if you want CU to "call" them
        ]
    )


def _build_gemini_contents(task_spec: Dict[str, Any]):
    """
    Build a user message that tells CU exactly what to do in one pass.
    Simple instruction to check the webpage for errors.
    """
    from google import genai

    url = task_spec.get("target_url")

    # Simple instruction for error checking
    user_text = f"Check the webpage for errors"

    return [
        genai.types.Content(
            role="user",
            parts=[genai.types.Part(text=user_text)],
        )
    ]


def _cu_to_playwright_actions(task_spec: Dict[str, Any], cu_raw: Any, run_id: str) -> List[Dict[str, Any]]:
    """
    Translate CU function_calls to our available Playwright action list:
      hover, click, get_computed_style, measure_hover_metrics,
      get_bounding_client_rect, get_text, current_url, screenshot

    Map CU actions to available playwright functions for error checking.
    """
    # Available functions from actions.py
    allowed = {"hover", "click", "get_computed_style", "measure_hover_metrics",
               "get_bounding_client_rect", "get_text", "current_url", "screenshot"}

    # Parse CU function calls (defensive: handle candidates/parts variability)
    function_names = []
    try:
        # cu_raw is a genai object; we saved a JSON-safe copy above
        safe = _safe_jsonify(cu_raw)
        for cand in (safe.get("candidates") or []):
            content = cand.get("content") or {}
            for part in (content.get("parts") or []):
                fc = part.get("function_call")
                if fc and isinstance(fc, dict):
                    name = fc.get("name")
                    if name:
                        function_names.append(name)
    except Exception:
        pass

    actions: List[Dict[str, Any]] = []

    # Map CU function calls to available playwright actions
    for fn in function_names:
        lower = fn.lower()
        if "hover" in lower:
            actions.append({"fn": "hover", "args": {"selector": "body"}})
        elif "click" in lower:
            actions.append({"fn": "click", "args": {"selector": "body"}})
        elif "screenshot" in lower:
            actions.append({"fn": "screenshot", "args": {"run_id": run_id, "label": "error_check"}})

    # Default actions for error checking if no specific actions found
    if not actions:
        actions = [
            {"fn": "screenshot", "args": {"run_id": run_id, "label": "error_check"}},
            {"fn": "get_text", "args": {"selector": "body"}},
            {"fn": "current_url", "args": {}},
        ]

    # Ensure we only return functions we support
    actions = [a for a in actions if a.get("fn") in allowed]
    return actions


def _default_error_check_actions(task_spec: Dict[str, Any], run_id: str) -> List[Dict[str, Any]]:
    """Default actions for error checking when no specific actions are found."""
    return [
        {"fn": "screenshot", "args": {"run_id": run_id, "label": "error_check"}},
        {"fn": "get_text", "args": {"selector": "body"}},
        {"fn": "current_url", "args": {}},
    ]


def _finalize_failure(run_dir: Path, run_id: str, *, errors: List[str], observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    result = {
        "run_id": run_id,
        "success": False,
        "summary": {
            "target_met": False,
            "steps_used": 1,
            "final_url": None
        },
        "observations": observations,
        "errors": errors,
        "artifacts": {
            "screenshots_dir": str(run_dir),
            "action_log": str(run_dir / "step-1.json"),
        },
    }
    save_result(run_dir, result)
    update_status(run_dir, {"state": "done", "step": 1, "success": False})
    return result


def _save_json(path: Path, obj: Any):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def _safe_jsonify(genai_obj: Any) -> Dict[str, Any]:
    """
    Convert genai Response-like objects into JSON-safe dicts.
    We use a permissive approach—if attributes aren’t present, we return what we can.
    """
    try:
        # Many genai objects have .to_dict()
        if hasattr(genai_obj, "to_dict"):
            return genai_obj.to_dict()
    except Exception:
        pass
    try:
        # Fallback: stringify then parse where possible
        return json.loads(json.dumps(genai_obj, default=_json_default))
    except Exception:
        return {"raw": str(genai_obj)}


def _json_default(o):
    # generic fallback for objects not serializable
    return getattr(o, "__dict__", str(o))
