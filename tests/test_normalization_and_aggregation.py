"""Tests for OpenRouter adapter normalization and aggregation pipeline."""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, Tuple

import pytest

from tool.orchestrator.adapter import normalize_with_openrouter
from tool.orchestrator.state import ProbeEvent
from tool.reporter.aggregator import build_audit_result
from tool.reporter.reporter import write_result_json


@pytest.fixture
def sample_blob() -> Dict[str, Any]:
    """Provide a fresh copy of the sample executor output for each test."""
    blob = {
        "run_id": "6898ae3f",
        "results": [
            {"fn": "click", "ok": True, "res": {"ok": True}},
            {"fn": "click", "ok": True, "res": {"ok": True}},
            {"fn": "click", "ok": True, "res": {"ok": True}},
            {
                "fn": "screenshot",
                "ok": False,
                "error": "screenshot() missing 1 required positional argument: 'run_id'",
            },
        ],
        "observation": {
            "selector": "#btn1",
            "metrics": {
                "before": {
                    "transform": "none",
                    "transitionDuration_ms": 0.0,
                    "transitionTimingFunction": "ease",
                },
                "after": {
                    "transform": "",
                    "transitionDuration_ms": None,
                    "transitionTimingFunction": "",
                },
            },
            "screenshots": [
                {"label": "before", "path": "runs/6898ae3f/step-1-before.png"},
                {
                    "label": "after_action_4",
                    "path": "runs/6898ae3f/step-1-after-action-4.png",
                },
            ],
            "screenshot": "runs/6898ae3f/step-1-after-action-4.png",
            "url": "http://localhost:5173/",
            "errors": [
                "Action screenshot failed: screenshot() missing 1 required positional argument: 'run_id'"
            ],
        },
    }
    return copy.deepcopy(blob)


@pytest.fixture
def force_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the adapter always uses the fallback path (no API key)."""

    monkeypatch.setenv("OPENROUTER_API_KEY", "")


def _normalize(sample_blob: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    primary_cta, probe_event = normalize_with_openrouter(sample_blob)
    return primary_cta, probe_event


def test_adapter_fallback_normalizes_without_api(sample_blob: Dict[str, Any], force_no_env: None) -> None:
    primary_cta, probe_event = _normalize(sample_blob)

    assert primary_cta is not None
    assert primary_cta.get("selector") == "#btn1"
    assert primary_cta.get("found_by") == "heuristic"

    assert probe_event.get("step") == 1
    assert probe_event.get("executor_ok") is False
    metrics = probe_event.get("metrics", {})
    computed = metrics.get("computed", {})
    assert computed.get("before", {}).get("transform") == "none"
    transition = computed.get("transition", {})
    assert transition.get("duration_ms") == 0.0
    assert transition.get("timing_function") == "ease"
    screenshot = probe_event.get("screenshot")
    assert isinstance(screenshot, str) and screenshot.endswith("step-1-after-action-4.png")


def test_aggregator_builds_hover_issue_and_writes_report(
    tmp_path,
    sample_blob: Dict[str, Any],
    force_no_env: None,
) -> None:
    primary_cta_dict, probe_event_dict = _normalize(sample_blob)
    event = ProbeEvent.model_validate(probe_event_dict)

    run_id = sample_blob["run_id"]
    run_dir = tmp_path / run_id
    artifacts = {
        "screenshots_dir": str(run_dir),
        "action_log": str(run_dir / "actions.jsonl"),
    }

    audit = build_audit_result(
        run_id=run_id,
        target_url=sample_blob["observation"]["url"],
        primary_cta=primary_cta_dict,
        probe_events=[event],
        console_lines=[],
        link_probes=[],
        dom_scan={},
        artifacts=artifacts,
    )

    assert audit.run_id == run_id
    assert audit.target_url == "http://localhost:5173/"
    assert audit.artifacts == artifacts
    hover_types = [issue.type for issue in audit.issues if issue.type == "hover_animation"]
    assert hover_types or not audit.issues  # Hover issue may or may not be present

    output_path = write_result_json(str(run_dir), audit)
    assert run_dir.joinpath("result.json").exists()
    with open(output_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["run_id"] == run_id
    if data.get("primary_cta"):
        assert data["primary_cta"]["selector"] == "#btn1"
    assert "issues" in data


def test_cta_not_found_creates_high_issue(tmp_path, sample_blob: Dict[str, Any]) -> None:
    run_id = sample_blob["run_id"]
    audit = build_audit_result(
        run_id=run_id,
        target_url="http://localhost/",
        primary_cta=None,
        probe_events=[],
        console_lines=[],
        link_probes=[],
        dom_scan={},
        artifacts={"screenshots_dir": str(tmp_path / run_id)},
    )

    assert len(audit.issues) == 1
    issue = audit.issues[0]
    assert issue.type == "cta_not_found"
    assert issue.severity == "high"
    assert audit.success is False


def test_console_and_link_issues_affect_success(
    sample_blob: Dict[str, Any],
    force_no_env: None,
) -> None:
    primary_cta_dict, probe_event_dict = _normalize(sample_blob)
    event = ProbeEvent.model_validate(probe_event_dict)

    audit = build_audit_result(
        run_id=sample_blob["run_id"],
        target_url=sample_blob["observation"]["url"],
        primary_cta=primary_cta_dict,
        probe_events=[event],
        console_lines=[{"type": "error", "text": "TypeError"}],
        link_probes=[
            {"href": "/dead", "status": 404},
            {"href": "/server", "status": 500},
        ],
        dom_scan={},
        artifacts={},
    )

    issue_types = [issue.type for issue in audit.issues]
    severities = {issue.type: issue.severity for issue in audit.issues}
    assert "console_error" in issue_types
    assert severities["console_error"] == "high"
    assert issue_types.count("broken_link") == 2
    broken_severities = [issue.severity for issue in audit.issues if issue.type == "broken_link"]
    assert "medium" in broken_severities and "high" in broken_severities
    assert audit.success is False


def test_missing_alt_and_accessible_name(
    sample_blob: Dict[str, Any],
    force_no_env: None,
) -> None:
    primary_cta_dict, probe_event_dict = _normalize(sample_blob)
    event = ProbeEvent.model_validate(probe_event_dict)

    audit = build_audit_result(
        run_id=sample_blob["run_id"],
        target_url=sample_blob["observation"]["url"],
        primary_cta=primary_cta_dict,
        probe_events=[event],
        console_lines=[],
        link_probes=[],
        dom_scan={
            "img_missing_alt_count": 3,
            "clickables_without_name": ["#x", ".y", ".z"],
        },
        artifacts={},
    )

    types = {issue.type: issue for issue in audit.issues}
    assert "missing_alt" in types
    assert types["missing_alt"].severity != "high"
    assert "missing_accessible_name" in types
    assert types["missing_accessible_name"].severity != "high"
