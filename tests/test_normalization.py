from copy import deepcopy

from tool.orchestrator.adapter import normalize_with_openrouter
from tool.orchestrator.state import (
    AuditResult,
    Issue,
    PrimaryCTA,
    ProbeEvent,
)


def test_pydantic_round_trip():
    probe = ProbeEvent(
        step=1,
        action_plan=[{"fn": "hover", "args": {"selector": "#btn1"}}],
        executor_ok=True,
        metrics={
            "computed": {
                "before": {"transform": "none"},
                "after": {"transform": "scale(1.02)"},
                "transition": {"duration_ms": 120, "timing_function": "ease"},
            },
            "bbox": None,
            "overlaps": [],
            "url": "http://localhost",
        },
        screenshot="path/to/screenshot.png",
        notes=None,
        errors=[],
    )
    payload = probe.model_dump()
    restored = ProbeEvent.model_validate(payload)
    assert restored == probe

    issue = Issue(
        id="hover-001",
        type="hover_animation",
        severity="medium",
        selector="#btn1",
        summary="Example",
        evidence={"foo": "bar"},
        suggested_fix="Fix it",
    )
    issue_dump = issue.model_dump()
    assert Issue.model_validate(issue_dump) == issue

    audit = AuditResult(
        run_id="test-run",
        success=True,
        target_url="http://localhost",
        primary_cta=PrimaryCTA(selector="#btn1", found_by="heuristic", confidence=0.8),
        issues=[issue],
        artifacts={"screenshots": {"before": "a.png", "after": "b.png"}},
    )
    audit_dump = audit.model_dump()
    assert AuditResult.model_validate(audit_dump) == audit


def test_normalize_with_openrouter_fallback():
    raw = {
        "run_id": "abc123",
        "results": [
            {"fn": "hover", "ok": True, "args": {"selector": "#btn1"}},
            {"fn": "screenshot", "ok": True, "args": {"label": "after"}},
        ],
        "observation": {
            "selector": "#btn1",
            "metrics": {
                "before": {
                    "transform": "none",
                    "transitionDuration_ms": 70,
                    "transitionTimingFunction": "linear",
                },
                "after": {
                    "transform": "scale(1.01)",
                    "transitionDuration_ms": 70,
                    "transitionTimingFunction": "linear",
                },
            },
            "screenshots": [{"path": "runs/abc/before.png"}, {"path": "runs/abc/after.png"}],
            "screenshot": "runs/abc/after.png",
            "url": "http://localhost:5173/",
            "errors": [],
        },
        "step": 1,
    }

    primary, event = normalize_with_openrouter(deepcopy(raw))
    assert isinstance(event, dict)
    validated = ProbeEvent.model_validate(event)
    assert validated.step == 1
    assert validated.executor_ok is True
    assert validated.metrics["computed"]["after"]["transform"] == "scale(1.01)"
    assert primary["selector"] == "#btn1"
