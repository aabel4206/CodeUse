"""Example script that normalizes executor output and produces an AuditResult."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from tool.orchestrator.adapter import normalize_with_openrouter
from tool.orchestrator.state import ProbeEvent
from tool.reporter.aggregator import build_audit_result
from tool.reporter.reporter import write_result_json


def _read_executor_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python examples/normalize_exec.py <executor_json>")
        return 1

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"File not found: {input_path}")
        return 1

    raw_blob = _read_executor_json(input_path)

    primary_cta_dict, probe_event_dict = normalize_with_openrouter(raw_blob)

    probe_events: List[ProbeEvent] = []
    try:
        probe_events.append(ProbeEvent.model_validate(probe_event_dict))
    except Exception as exc:
        print(f"Warning: failed to validate probe event via Pydantic ({exc}). Using best-effort dict.")
        try:
            probe_events.append(ProbeEvent(**probe_event_dict))  # type: ignore[arg-type]
        except Exception:
            pass

    console_lines = raw_blob.get("console", []) or []
    link_probes = raw_blob.get("links", []) or []
    dom_scan = raw_blob.get("dom_scan") or {}

    observation = raw_blob.get("observation", {}) or {}
    target_url = (
        raw_blob.get("target_url")
        or observation.get("url")
        or os.getenv("DEFAULT_TARGET_URL")
        or "about:blank"
    )

    run_id = raw_blob.get("run_id") or input_path.stem
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    audit = build_audit_result(
        run_id=run_id,
        target_url=target_url,
        primary_cta=primary_cta_dict,
        probe_events=probe_events,
        console_lines=console_lines,
        link_probes=link_probes,
        dom_scan=dom_scan,
        artifacts={
            "screenshots_dir": str(run_dir),
            "action_log": str(run_dir / "actions.jsonl"),
        },
    )

    result_path = write_result_json(str(run_dir), audit)

    print("Primary CTA:")
    print(json.dumps(primary_cta_dict, indent=2, ensure_ascii=False))
    print("Probe Event:")
    print(json.dumps(probe_event_dict, indent=2, ensure_ascii=False))
    print(f"Audit result written to {result_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

