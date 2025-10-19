from tool.orchestrator.state import PrimaryCTA, ProbeEvent
from tool.reporter.aggregator import build_audit_result


def _base_probe(**overrides):
    probe = ProbeEvent(
        step=1,
        action_plan=[],
        executor_ok=True,
        metrics={
            "computed": {
                "before": {"transform": "none"},
                "after": {"transform": "scale(1.01)"},
                "transition": {"duration_ms": 70, "timing_function": "linear"},
            },
            "bbox": None,
            "overlaps": [],
            "url": "http://localhost",
        },
        screenshot="path/to.png",
        notes=None,
        errors=[],
    )
    data = probe.model_dump()
    data.update(overrides)
    return ProbeEvent.model_validate(data)


def test_build_audit_result_hover_issue():
    probe = _base_probe()
    audit = build_audit_result(
        run_id="hover-run",
        target_url="http://localhost",
        primary_cta=PrimaryCTA(selector="#btn1", found_by="heuristic", confidence=0.8).model_dump(),
        probe_events=[probe],
        console_lines=[],
        link_probes=[],
        dom_scan=None,
        artifacts={},
    )
    assert any(issue.type == "hover_animation" for issue in audit.issues)
    assert audit.summary


def test_build_audit_result_console_issue():
    probe = _base_probe(
        metrics={
            "computed": {
                "before": {"transform": "none"},
                "after": {"transform": "scale(1.05)"},
                "transition": {"duration_ms": 180, "timing_function": "ease-out"},
            },
            "bbox": None,
            "overlaps": [],
            "url": "http://localhost",
        }
    )

    audit = build_audit_result(
        run_id="console-run",
        target_url="http://localhost",
        primary_cta=PrimaryCTA(selector="#btn1", found_by="heuristic", confidence=0.8).model_dump(),
        probe_events=[probe],
        console_lines=[{"type": "error", "message": "ReferenceError"}],
        link_probes=[],
        dom_scan=None,
        artifacts={},
    )
    assert any(issue.type == "console_error" for issue in audit.issues)
    assert audit.summary


def test_build_audit_result_broken_link_issue():
    probe = _base_probe(
        metrics={
            "computed": {
                "before": {"transform": "none"},
                "after": {"transform": "scale(1.05)"},
                "transition": {"duration_ms": 180, "timing_function": "ease-out"},
            },
            "bbox": None,
            "overlaps": [],
            "url": "http://localhost",
        }
    )

    audit = build_audit_result(
        run_id="links-run",
        target_url="http://localhost",
        primary_cta=PrimaryCTA(selector="#btn1", found_by="heuristic", confidence=0.8).model_dump(),
        probe_events=[probe],
        console_lines=[],
        link_probes=[{"url": "http://localhost/broken", "status": 404}],
        dom_scan=None,
        artifacts={},
    )
    assert any(issue.type == "broken_link" for issue in audit.issues)
    assert audit.summary
