"""
Aggregator that normalizes raw executor/orchestrator artifacts into an AuditResult.
Rules applied include hover animation spec, console errors, broken links, alt text,
accessible names, and overlap/small click target.
"""

from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel

from tool.orchestrator.state import (
    PrimaryCTA,
    ProbeEvent,
    Issue,
    AuditResult,
    make_issue_id,
)


SPEC: Dict[str, Any] = {
    "hover": {
        "scale_min": 1.03,
        "scale_max": 1.07,
        "duration_min": 120,
        "duration_max": 200,
        "timings": {"ease", "ease-out"},
    },
    "min_click_size": 44,
}


def _extract_scale(transform_str: Optional[str]) -> Optional[float]:
    """Parse scale from a CSS transform string.

    Accepts formats like:
      - "scale(1.05)" or "scale(1.05, 1.05)"
      - "matrix(a, b, c, d, e, f)" and returns a (assumes a==d for uniform scale)
    """
    if not transform_str:
        return None
    s = str(transform_str).strip()
    # Direct scale()
    import re

    m = re.search(r"scale\s*\(\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)", s)
    if m:
        try:
            sx = float(m.group(1))
            sy = float(m.group(2)) if m.group(2) else sx
            # Return average if both provided
            return (sx + sy) / 2.0
        except Exception:
            return None

    # matrix(a, b, c, d, e, f) -> use a
    m = re.search(r"matrix\s*\(\s*([-0-9.]+)\s*,\s*[-0-9.]+\s*,\s*[-0-9.]+\s*,\s*([-0-9.]+)\s*,\s*[-0-9.]+\s*,\s*[-0-9.]+\s*\)", s)
    if m:
        try:
            a = float(m.group(1))
            # d = float(m.group(2))  # unused; assume uniform for UI hover
            return a
        except Exception:
            return None

    return None


def _pick_last_ok_event(events: List[ProbeEvent]) -> Optional[ProbeEvent]:
    """Return the last ProbeEvent with executor_ok=True and metrics present."""
    for ev in reversed(events or []):
        try:
            if ev and getattr(ev, "executor_ok", False) and getattr(ev, "metrics", None):
                return ev
        except Exception:
            continue
    return None


def _issue_hover_animation(step_evt: ProbeEvent, selector: str, n: int) -> Optional[Issue]:
    """Validate hover animation against SPEC bounds; returns an Issue if out-of-spec."""
    try:
        metrics = step_evt.metrics or {}
        computed = metrics.get("computed") or {}

        before = computed.get("before") or {}
        after = computed.get("after") or {}
        transform_before = before.get("transform")
        transform_after = after.get("transform")
        scale_before = _extract_scale(transform_before)
        scale_after = _extract_scale(transform_after)

        # Duration and timing can be surfaced in multiple shapes
        transition = computed.get("transition") or {}
        duration_ms = (
            transition.get("duration_ms")
            or metrics.get("transition_duration_ms")
            or computed.get("transition_duration_ms")
        )
        timing = (
            transition.get("timing_function")
            or metrics.get("timing")
            or computed.get("timing_function")
        )

        # If we cannot extract any hover specifics, skip emitting an issue
        if scale_after is None and duration_ms is None and timing is None:
            return None

        bounds = SPEC["hover"]
        failures: List[str] = []

        if scale_after is not None:
            if not (bounds["scale_min"] <= scale_after <= bounds["scale_max"]):
                failures.append(
                    f"scale {scale_after} outside {bounds['scale_min']}..{bounds['scale_max']}"
                )
        if duration_ms is not None:
            try:
                d = float(duration_ms)
                if not (bounds["duration_min"] <= d <= bounds["duration_max"]):
                    failures.append(
                        f"duration {d}ms outside {bounds['duration_min']}..{bounds['duration_max']}ms"
                    )
            except Exception:
                failures.append("invalid transition duration value")
        if timing is not None:
            t = str(timing).strip()
            if t and t not in bounds["timings"]:
                failures.append(f"timing '{t}' not in {sorted(bounds['timings'])}")

        if not failures:
            return None

        evidence = {
            "metrics": {
                "scale_before": scale_before,
                "scale_after": scale_after,
                "transition_duration_ms": duration_ms,
                "timing_function": timing,
            },
        }
        if step_evt.screenshot:
            evidence["screenshot"] = step_evt.screenshot

        return Issue(
            id=make_issue_id("hover", n),
            type="hover_animation",
            severity="medium",
            selector=selector,
            summary="Hover animation out of spec: " + "; ".join(failures),
            evidence=evidence,
            suggested_fix="Increase transform scale to ~1.05 and duration to ~150ms ease-out.",
        )
    except Exception:
        return None


def _issue_console_errors(console_lines: List[Dict[str, Any]], n: int) -> Optional[Issue]:
    try:
        errors = [c for c in (console_lines or []) if str(c.get("type", "")).lower() == "error"]
        if not errors:
            return None
        top = errors[:3]
        msgs = [str(e.get("message") or e.get("text") or "") for e in top]
        evidence = {"errors": msgs}
        return Issue(
            id=make_issue_id("console", n),
            type="console_error",
            severity="high",
            selector=None,
            summary=f"{len(errors)} console error(s) detected",
            evidence=evidence,
            suggested_fix="Fix JavaScript error(s) logged in console.",
        )
    except Exception:
        return None


def _issue_broken_links(link_probes: List[Dict[str, Any]], n: int) -> List[Issue]:
    issues: List[Issue] = []
    try:
        for i, lp in enumerate(link_probes or []):
            try:
                status = int(lp.get("status", 0))
            except Exception:
                continue
            if status >= 400:
                sev = "high" if status >= 500 else "medium"
                url = lp.get("url") or lp.get("href") or ""
                issues.append(
                    Issue(
                        id=make_issue_id("link", n + i),
                        type="broken_link",
                        severity=sev,
                        selector=None,
                        summary=f"Broken link {status}: {url}",
                        evidence={"url": url, "status": status},
                        suggested_fix="Remove or update dead links: check target URLs or server.",
                    )
                )
    except Exception:
        return issues
    return issues


def _issue_missing_alt(dom_scan: Dict[str, Any], n: int) -> Optional[Issue]:
    try:
        count = int(dom_scan.get("img_missing_alt_count", 0)) if dom_scan else 0
        if count <= 0:
            return None
        return Issue(
            id=make_issue_id("alt", n),
            type="missing_alt",
            severity="medium",
            selector=None,
            summary=f"{count} image(s) missing alt text",
            evidence={"img_missing_alt_count": count},
            suggested_fix="Add alt attributes to images.",
        )
    except Exception:
        return None


def _issue_missing_accessible_name(dom_scan: Dict[str, Any], n: int) -> Optional[Issue]:
    try:
        items = (dom_scan or {}).get("clickables_without_name") or []
        if not isinstance(items, list) or not items:
            return None
        sample = items[:5]
        return Issue(
            id=make_issue_id("a11yname", n),
            type="missing_accessible_name",
            severity="medium",
            selector=None,
            summary=f"{len(items)} clickable element(s) without accessible name",
            evidence={"sample": sample, "total": len(items)},
            suggested_fix="Provide aria-label or visible text for clickable elements.",
        )
    except Exception:
        return None


def _issue_overlap_or_small_target(
    bbox: Optional[Dict[str, Any]], overlaps: List[Dict[str, Any]], selector: str, n: int
) -> List[Issue]:
    issues: List[Issue] = []
    try:
        min_sz = SPEC["min_click_size"]
        if bbox and isinstance(bbox, dict):
            try:
                w = float(bbox.get("width", 0))
                h = float(bbox.get("height", 0))
                if w < min_sz or h < min_sz:
                    issues.append(
                        Issue(
                            id=make_issue_id("target", n),
                            type="small_click_target",
                            severity="medium",
                            selector=selector,
                            summary=f"Click target too small: {int(w)}×{int(h)} (< {min_sz}px)",
                            evidence={"bbox": bbox},
                            suggested_fix="Increase target size to at least 44×44.",
                        )
                    )
            except Exception:
                pass

        if overlaps and isinstance(overlaps, list):
            if overlaps:
                issues.append(
                    Issue(
                        id=make_issue_id("overlap", n + len(issues)),
                        type="overlap",
                        severity="medium",
                        selector=selector,
                        summary=f"Element overlaps detected ({len(overlaps)})",
                        evidence={"overlaps": overlaps},
                        suggested_fix="Resolve layout overlap by adjusting spacing/z-index.",
                    )
                )
    except Exception:
        return issues
    return issues


def build_audit_result(
    run_id: str,
    target_url: str,
    primary_cta: Optional[Dict[str, Any]],
    probe_events: List[ProbeEvent],
    console_lines: List[Dict[str, Any]],
    link_probes: List[Dict[str, Any]],
    dom_scan: Optional[Dict[str, Any]],
    artifacts: Dict[str, Any],
) -> AuditResult:
    """
    Normalize raw CU/executor artifacts into a canonical AuditResult.
    Rules applied:
      - Hover animation spec
      - Console errors
      - Broken links
      - Missing alt
      - Missing accessible name
      - Overlap / small click target
    Missing inputs should not crash; just skip the rule and continue.
    """
    issues: List[Issue] = []
    n = 1

    # Primary CTA handling
    cta: Optional[PrimaryCTA] = None
    if primary_cta:
        try:
            cta = PrimaryCTA.model_validate(primary_cta)
        except Exception:
            cta = None

    if cta is None:
        issues.append(
            Issue(
                id=make_issue_id("cta", n),
                type="cta_not_found",
                severity="high",
                selector=None,
                summary="Primary CTA not found",
                evidence={"reason": "No primary CTA provided by orchestrator"},
                suggested_fix="Ensure a primary call-to-action exists and is detectable.",
            )
        )
        n += 1
    else:
        # Hover animation rule
        last_ok = _pick_last_ok_event(probe_events or [])
        if last_ok:
            hover_issue = _issue_hover_animation(last_ok, cta.selector, n)
            if hover_issue:
                issues.append(hover_issue)
                n += 1

            # Overlap / small target using bbox/overlaps if available
            metrics = last_ok.metrics or {}
            bbox = metrics.get("bbox") or metrics.get("element_bbox")
            overlaps = metrics.get("overlaps") or []
            ov_issues = _issue_overlap_or_small_target(bbox, overlaps, cta.selector, n)
            if ov_issues:
                issues.extend(ov_issues)
                n += len(ov_issues)

    # Console errors
    cons_issue = _issue_console_errors(console_lines or [], n)
    if cons_issue:
        issues.append(cons_issue)
        n += 1

    # Broken links
    link_issues = _issue_broken_links(link_probes or [], n)
    if link_issues:
        issues.extend(link_issues)
        n += len(link_issues)

    # Missing alt
    alt_issue = _issue_missing_alt(dom_scan or {}, n)
    if alt_issue:
        issues.append(alt_issue)
        n += 1

    # Missing accessible name
    name_issue = _issue_missing_accessible_name(dom_scan or {}, n)
    if name_issue:
        issues.append(name_issue)
        n += 1

    # Determine success (no high severity issues)
    has_high = any(i.severity == "high" for i in issues)
    success = not has_high

    summary_parts: List[str] = []
    if issues:
        summary_parts.append(f"Detected {len(issues)} issue(s).")
        for issue in issues:
            summary_parts.append(f"{issue.id}: {issue.summary}")
    else:
        last_ok = _pick_last_ok_event(probe_events or [])
        if last_ok:
            metrics = (last_ok.metrics or {}).get("computed") or {}
            after = metrics.get("after") or {}
            transition = metrics.get("transition") or {}
            transform = after.get("transform") or "none"
            duration = transition.get("duration_ms")
            timing = transition.get("timing_function")
            summary_parts.append(
                "No issues detected. Hover transform "
                f"{transform} with duration {duration} ms and timing {timing}."
            )
        else:
            summary_parts.append("No issues detected in available probe events.")

    audit = AuditResult(
        run_id=run_id,
        success=success,
        target_url=target_url,
        primary_cta=cta,
        issues=issues,
        summary=" ".join(summary_parts),
        artifacts=artifacts or {},
    )
    return audit
