"""Adapter that normalizes executor output into orchestrator schemas using OpenRouter."""

import json
import os
from typing import Any, Dict, Tuple

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import httpx


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")


SYSTEM_PROMPT = """You are a strict JSON normalizer for browser-execution traces.
Output ONLY JSON, NO prose. If a field is unknown use null.

Target schemas:

PrimaryCTA:
{
  "selector": string,
  "found_by": "gemini_cu" | "heuristic",
  "confidence": number,
  "rationale": string | null
}

ProbeEvent:
{
  "step": number,
  "action_plan": [{"fn": string, "args": object | null}, ...],
  "executor_ok": boolean,
  "metrics": {
    "computed": {
      "before": {"transform": string | null},
      "after":  {"transform": string | null},
      "transition": {
        "duration_ms": number | null,
        "timing_function": string | null
      }
    },
    "bbox": object | null,
    "overlaps": array | null,
    "url": string | null
  },
  "screenshot": string | null,
  "notes": string | null,
  "errors": [string, ...]
}

Rules:
- Convert camelCase to snake_case.
- If input has transitionDuration_ms or transitionTimingFunction, map to computed.transition.duration_ms and computed.transition.timing_function.
- executor_ok = all results[].ok are true AND observation.errors is empty.
- step defaults to 1 if not provided.
- screenshot = last available screenshot path from observation.screenshot or observation.screenshots[].
- If observation.selector exists, produce PrimaryCTA with found_by="heuristic", confidence=0.8 and a short rationale.
Return:
{
  "primary_cta": PrimaryCTA | null,
  "probe_event": ProbeEvent
}"""


def _strip_json(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        # remove as many wrapping fences as present
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
    return s.strip()


def _pick_first(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        # Treat empty strings as missing for timing fields, but keep falsy numbers like 0.0
        if isinstance(value, str) and value == "":
            continue
        return value
    return None


def _fallback_normalize(raw_executor_json: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    """Local best-effort mapper when OpenRouter is unavailable."""
    obs = raw_executor_json.get("observation", {}) or {}
    results = raw_executor_json.get("results", []) or []

    all_ok = all(bool(x.get("ok")) for x in results) and not bool(obs.get("errors"))

    # Last screenshot path
    screenshot = obs.get("screenshot")
    if not screenshot:
        shots = obs.get("screenshots") or []
        if isinstance(shots, list) and shots:
            last_shot = shots[-1]
            if isinstance(last_shot, dict):
                screenshot = last_shot.get("path") or last_shot.get("url")
            elif isinstance(last_shot, str):
                screenshot = last_shot

    metrics = obs.get("metrics") or {}
    before = metrics.get("before") or {}
    after = metrics.get("after") or {}

    transition_duration = _pick_first(
        before.get("transitionDuration_ms"),
        after.get("transitionDuration_ms"),
        metrics.get("transitionDuration_ms"),
    )
    transition_timing = _pick_first(
        before.get("transitionTimingFunction"),
        after.get("transitionTimingFunction"),
        metrics.get("transitionTimingFunction"),
    )

    action_plan = []
    for entry in results:
        if not isinstance(entry, dict):
            continue
        action_plan.append({
            "fn": entry.get("fn"),
            "args": entry.get("args"),
        })

    probe_event = {
        "step": raw_executor_json.get("step", 1) or 1,
        "action_plan": action_plan,
        "executor_ok": bool(all_ok),
        "metrics": {
            "computed": {
                "before": {"transform": before.get("transform")},
                "after": {"transform": after.get("transform")},
                "transition": {
                    "duration_ms": transition_duration,
                    "timing_function": transition_timing,
                },
            },
            "bbox": metrics.get("bbox") or metrics.get("element_bbox"),
            "overlaps": metrics.get("overlaps") or [],
            "url": obs.get("url"),
        },
        "screenshot": screenshot,
        "notes": obs.get("notes"),
        "errors": obs.get("errors") or [],
    }

    primary_cta = None
    selector = obs.get("selector")
    if selector:
        primary_cta = {
            "selector": selector,
            "found_by": "heuristic",
            "confidence": 0.8,
            "rationale": "Selector provided by executor observation",
        }

    return primary_cta, probe_event


def normalize_with_openrouter(raw_executor_json: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    """Normalize executor output to orchestrator schemas using OpenRouter; fallback locally."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": os.getenv("HTTP_REFERER", "http://localhost"),
        "X-Title": "codeuse-normalizer",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Here is the raw executor JSON:\n"
                + json.dumps(raw_executor_json, ensure_ascii=False),
            },
        ],
        "temperature": 0,
    }

    try:
        if not api_key:
            raise RuntimeError("missing OPENROUTER_API_KEY")

        with httpx.Client(timeout=60) as client:
            response = client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        normalized = json.loads(_strip_json(content))
        primary = normalized.get("primary_cta")
        event = normalized.get("probe_event") or {}
        if event is None:
            raise ValueError("probe_event missing from OpenRouter response")
        return primary, event
    except Exception:
        return _fallback_normalize(raw_executor_json)
