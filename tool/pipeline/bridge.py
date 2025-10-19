"""Bridge that connects adapter, aggregator, and reporter for Role C."""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from tool.orchestrator.adapter import normalize_with_openrouter
from tool.orchestrator.state import AuditResult, ProbeEvent
from tool.reporter.aggregator import build_audit_result
from tool.reporter.reporter import write_result_json


class BridgeOut(BaseModel):
    """Structured response returned by the pipeline bridge."""

    run_id: str
    result_json_path: str
    audit: AuditResult
    ui_payload: Dict[str, Any]


def _coerce_probe_event(probe_event_dict: Dict[str, Any]) -> ProbeEvent:
    """Best-effort conversion of adapter output into a ProbeEvent model."""

    try:
        return ProbeEvent.model_validate(probe_event_dict)
    except Exception:
        # Fall back to manual construction while preserving known fields.
        return ProbeEvent(
            step=probe_event_dict.get("step", 1) or 1,
            action_plan=list(probe_event_dict.get("action_plan", []) or []),
            executor_ok=bool(probe_event_dict.get("executor_ok", False)),
            metrics=probe_event_dict.get("metrics"),
            screenshot=probe_event_dict.get("screenshot"),
            notes=probe_event_dict.get("notes"),
            errors=list(probe_event_dict.get("errors", []) or []),
        )


def _make_ui_payload(audit: AuditResult) -> Dict[str, Any]:
    """Reduce AuditResult into a small, frontend-friendly dictionary."""

    try:
        sev_counts: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        issues_by_type: Dict[str, List[Dict[str, Any]]] = {}
        gallery: List[str] = []

        for issue in audit.issues:
            sev_counts[issue.severity] = sev_counts.get(issue.severity, 0) + 1
            evidence = issue.evidence or {}
            screenshot_path = evidence.get("screenshot")
            issues_by_type.setdefault(issue.type, []).append(
                {
                    "id": issue.id,
                    "severity": issue.severity,
                    "selector": issue.selector,
                    "summary": issue.summary,
                    "suggested_fix": issue.suggested_fix,
                    "screenshot": screenshot_path,
                }
            )
            if screenshot_path:
                gallery.append(screenshot_path)

        total_issues = sum(sev_counts.values())

        primary = audit.primary_cta
        cta_card = None
        if primary is not None:
            cta_card = {
                "selector": primary.selector,
                "found_by": primary.found_by,
                "confidence": primary.confidence,
                "rationale": primary.rationale,
            }

        return {
            "header": {
                "title": "CodeUse Audit",
                "target_url": audit.target_url,
                "success": audit.success,
                "severity_counts": sev_counts,
                "total_issues": total_issues,
            },
            "cta": cta_card,
            "issues_by_type": issues_by_type,
            "gallery": gallery[:12],
            "artifacts": audit.artifacts,
        }
    except Exception:
        return {
            "header": {
                "title": "CodeUse Audit",
                "target_url": audit.target_url,
                "success": False,
                "severity_counts": {"high": 0, "medium": 0, "low": 0},
                "total_issues": 0,
            },
            "cta": None,
            "issues_by_type": {},
            "gallery": [],
            "artifacts": audit.artifacts,
        }


def process_executor_result(
    raw_executor_json: Dict[str, Any],
    user_prompt: Optional[str] = None,
) -> BridgeOut:
    """Entry-point for the Role C pipeline bridge."""

    run_id = str(raw_executor_json.get("run_id") or "run").strip() or "run"
    observation = raw_executor_json.get("observation", {}) or {}
    target_url = raw_executor_json.get("target_url") or observation.get("url") or ""

    primary_cta_dict, probe_event_dict = normalize_with_openrouter(raw_executor_json)

    probe_events: List[ProbeEvent] = []
    if probe_event_dict:
        probe_events.append(_coerce_probe_event(probe_event_dict))

    console_lines = raw_executor_json.get("console") or raw_executor_json.get("console_lines") or []
    link_probes = raw_executor_json.get("link_probes") or raw_executor_json.get("links") or []
    dom_scan = raw_executor_json.get("dom_scan") or {}

    run_dir = pathlib.Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts: Dict[str, Any] = {
        "screenshots_dir": str(run_dir),
        "action_log": str(run_dir / "actions.jsonl"),
    }
    if user_prompt:
        artifacts["user_prompt"] = user_prompt

    audit = build_audit_result(
        run_id=run_id,
        target_url=target_url,
        primary_cta=primary_cta_dict,
        probe_events=probe_events,
        console_lines=console_lines,
        link_probes=link_probes,
        dom_scan=dom_scan,
        artifacts=artifacts,
    )

    result_json_path = write_result_json(str(run_dir), audit)
    ui_payload = _make_ui_payload(audit)

    return BridgeOut(
        run_id=run_id,
        result_json_path=result_json_path,
        audit=audit,
        ui_payload=ui_payload,
    )

