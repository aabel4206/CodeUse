"""Connectivity audit for the CodeUse pipeline."""

from __future__ import annotations

import ast
import compileall
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _get_docstring(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        module = ast.parse(_read_text(path))
        doc = ast.get_docstring(module)
        return (doc or "").strip()
    except Exception:
        return ""


def _list_py_files(rel_dir: str) -> List[Path]:
    base = PROJECT_ROOT / rel_dir
    files: List[Path] = []
    if not base.exists():
        return files
    for dirpath, _, filenames in os.walk(base):
        for name in filenames:
            if name.endswith(".py"):
                files.append(Path(dirpath, name).resolve())
    return sorted(files)


def _extract_imports(source_path: Path) -> Iterable[str]:
    source = _read_text(source_path)
    try:
        tree = ast.parse(source)
    except Exception:
        return []
    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("tool"):
                imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tool"):
                    imports.append(alias.name)
    return imports


def _find_call_sites(source_path: Path, symbols: Iterable[str]) -> Dict[str, List[str]]:
    lines = _read_text(source_path).splitlines()
    call_map = {sym: [] for sym in symbols}
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for sym in symbols:
            if f"{sym}(" in stripped:
                call_map[sym].append(f"{source_path.relative_to(PROJECT_ROOT)}:{idx}")
    return call_map


@contextmanager
def _force_adapter_fallback() -> Iterable[None]:
    key = os.environ.get("OPENROUTER_API_KEY")
    try:
        os.environ["OPENROUTER_API_KEY"] = ""
        yield
    finally:
        if key is None:
            os.environ.pop("OPENROUTER_API_KEY", None)
        else:
            os.environ["OPENROUTER_API_KEY"] = key


def _load_sample_executor_blob() -> Dict[str, Any]:
    candidate = PROJECT_ROOT / "examples" / "executor_out.json"
    if candidate.exists():
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "run_id": "demo1234",
        "results": [
            {"fn": "click", "ok": True, "res": {"ok": True}},
            {"fn": "screenshot", "ok": True, "res": {"ok": True}},
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
                    "transform": "scale(1.02)",
                    "transitionDuration_ms": 75.0,
                    "transitionTimingFunction": "linear",
                },
            },
            "screenshots": [
                {"label": "after", "path": "runs/demo1234/after.png"}
            ],
            "screenshot": "runs/demo1234/after.png",
            "url": "http://localhost:5173/",
            "errors": [],
        },
    }


def _print_section(title: str, lines: Iterable[str]) -> None:
    print(f"== {title} ==")
    for line in lines:
        print(line)
    print()


# ---------------------------------------------------------------------------
# Main audit logic
# ---------------------------------------------------------------------------


def main() -> int:
    # Import targets (capture errors)
    import_status: List[Tuple[str, bool, str]] = []
    try:
        from tool.orchestrator.adapter import normalize_with_openrouter
        import_status.append(("tool.orchestrator.adapter.normalize_with_openrouter", True, ""))
    except Exception as exc:  # pragma: no cover
        import_status.append(("tool.orchestrator.adapter.normalize_with_openrouter", False, str(exc)))
        normalize_with_openrouter = None  # type: ignore

    try:
        from tool.orchestrator.state import AuditResult, PrimaryCTA, ProbeEvent
        import_status.append(("tool.orchestrator.state", True, ""))
    except Exception as exc:  # pragma: no cover
        import_status.append(("tool.orchestrator.state", False, str(exc)))
        AuditResult = PrimaryCTA = ProbeEvent = None  # type: ignore

    try:
        from tool.reporter.aggregator import build_audit_result
        import_status.append(("tool.reporter.aggregator.build_audit_result", True, ""))
    except Exception as exc:  # pragma: no cover
        import_status.append(("tool.reporter.aggregator.build_audit_result", False, str(exc)))
        build_audit_result = None  # type: ignore

    try:
        from tool.reporter.reporter import write_result_json
        import_status.append(("tool.reporter.reporter.write_result_json", True, ""))
    except Exception as exc:  # pragma: no cover
        import_status.append(("tool.reporter.reporter.write_result_json", False, str(exc)))
        write_result_json = None  # type: ignore

    try:
        from tool.pipeline.bridge import process_executor_result
        import_status.append(("tool.pipeline.bridge.process_executor_result", True, ""))
    except Exception as exc:  # pragma: no cover
        import_status.append(("tool.pipeline.bridge.process_executor_result", False, str(exc)))
        process_executor_result = None  # type: ignore

    # Module overview using os.walk and docstrings
    overview_lines: List[str] = []
    key_modules = {
        "tool/orchestrator/adapter.py": "Adapter: Normalize executor traces",
        "tool/orchestrator/loop.py": "Loop: Orchestration entry",
        "tool/orchestrator/state.py": "State & shared schemas",
        "tool/reporter/aggregator.py": "Aggregator rules",
        "tool/reporter/reporter.py": "Reporter utilities",
        "tool/pipeline/bridge.py": "Role C bridge",
    }
    for rel, label in key_modules.items():
        path = PROJECT_ROOT / rel
        status = "present" if path.exists() else "missing"
        doc = _get_docstring(path)
        doc_part = f" doc: {doc.splitlines()[0]}" if doc else ""
        overview_lines.append(f"- {rel} [{status}] — {label}{doc_part}")

    # executor directory contents
    exe_files = _list_py_files("tool/executor")
    if exe_files:
        overview_lines.append(f"- tool/executor/ [{len(exe_files)} py files]")
        for file in exe_files:
            overview_lines.append(f"  - {file.relative_to(PROJECT_ROOT)}")
    else:
        overview_lines.append("- tool/executor/ missing")

    llm_dir = PROJECT_ROOT / "tool" / "llm_parse"
    if llm_dir.exists():
        overview_lines.append("- tool/llm_parse/ present (deprecated path)")
    else:
        overview_lines.append("- tool/llm_parse/ missing (deprecated path)")

    _print_section("MODULE OVERVIEW", overview_lines)

    # Import graph via os.walk
    graph_lines: List[str] = []
    for py_path in PROJECT_ROOT.rglob("*.py"):
        if py_path.is_dir():
            continue
        if "__pycache__" in py_path.parts:
            continue
        imports = list(_extract_imports(py_path))
        if imports:
            graph_lines.append(
                f"{py_path.relative_to(PROJECT_ROOT)} -> {', '.join(sorted(set(imports)))}"
            )
    _print_section("IMPORT GRAPH (tool.*)", graph_lines)

    # Call sites for critical functions
    symbols = [
        "normalize_with_openrouter",
        "build_audit_result",
        "write_result_json",
        "process_executor_result",
    ]
    call_lines: List[str] = []
    aggregated_calls: Dict[str, List[str]] = {sym: [] for sym in symbols}
    for py_path in PROJECT_ROOT.rglob("*.py"):
        if py_path.is_dir():
            continue
        for sym, locations in _find_call_sites(py_path, symbols).items():
            aggregated_calls[sym].extend(locations)
    for sym in symbols:
        call_lines.append(f"{sym} call sites:")
        for loc in sorted(aggregated_calls[sym]):
            call_lines.append(f"  - {loc}")
    _print_section("CALL SITES", call_lines)

    # Environment info
    env_lines: List[str] = []
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        keys = []
        for raw in _read_text(env_path).splitlines():
            if "=" in raw and not raw.strip().startswith("#"):
                key = raw.split("=", 1)[0].strip()
                if key.startswith("OPENROUTER"):
                    keys.append(key)
        env_lines.append(f".env present ({env_path})")
        env_lines.append(f"OPENROUTER keys: {', '.join(sorted(set(keys)) or ['none'])}")
    else:
        env_lines.append(".env missing")
    _print_section("ENVIRONMENT", env_lines)

    # Compileall verification
    compile_success = compileall.compile_dir(str(PROJECT_ROOT), quiet=1)
    _print_section("COMPILEALL", [f"compile_dir success: {bool(compile_success)}"])

    # Print import statuses
    import_lines = [
        f"{name}: {'OK' if ok else 'FAIL'}{(' — ' + err) if (err and not ok) else ''}"
        for name, ok, err in import_status
    ]
    _print_section("IMPORT CHECKS", import_lines)

    # Pipeline dry-run
    checklist: List[Tuple[str, bool, str]] = []
    bridge_out = None
    try:
        sample_blob = _load_sample_executor_blob()
        with _force_adapter_fallback():
            # Adapter step
            if normalize_with_openrouter is None:
                raise RuntimeError("normalize_with_openrouter unavailable")
            primary_cta_dict, probe_event_dict = normalize_with_openrouter(sample_blob)
            adapter_ok = probe_event_dict is not None
            checklist.append(("Executor JSON -> Adapter", adapter_ok, ""))

            if not adapter_ok:
                raise RuntimeError("Adapter failed to return probe event")

            # Aggregator step
            if build_audit_result is None or ProbeEvent is None:
                raise RuntimeError("Aggregator dependencies missing")

            agg_run_id = f"{sample_blob.get('run_id', 'demo')}--audit"
            agg_run_dir = PROJECT_ROOT / "runs" / agg_run_id
            agg_run_dir.mkdir(parents=True, exist_ok=True)

            try:
                probe_event_model = ProbeEvent.model_validate(probe_event_dict)
            except Exception as exc:  # pragma: no cover
                probe_event_model = ProbeEvent(
                    step=1,
                    action_plan=list(probe_event_dict.get("action_plan", []) or []),
                    executor_ok=bool(probe_event_dict.get("executor_ok", False)),
                    metrics=probe_event_dict.get("metrics"),
                    screenshot=probe_event_dict.get("screenshot"),
                    notes=probe_event_dict.get("notes"),
                    errors=list(probe_event_dict.get("errors", []) or []),
                )

            audit = build_audit_result(
                run_id=agg_run_id,
                target_url=sample_blob.get("observation", {}).get("url", ""),
                primary_cta=primary_cta_dict,
                probe_events=[probe_event_model],
                console_lines=sample_blob.get("console", []),
                link_probes=sample_blob.get("links", sample_blob.get("link_probes", [])),
                dom_scan=sample_blob.get("dom_scan", {}),
                artifacts={"screenshots_dir": str(agg_run_dir)},
            )
            aggregator_ok = isinstance(audit, AuditResult)
            checklist.append(("Adapter -> Aggregator", aggregator_ok, ""))

            # Reporter step
            if write_result_json is None:
                raise RuntimeError("write_result_json unavailable")

            result_path = write_result_json(str(agg_run_dir), audit)
            reporter_ok = Path(result_path).exists()
            checklist.append(("Aggregator -> Reporter (result.json)", reporter_ok, result_path))

            # Bridge step
            if process_executor_result is None:
                raise RuntimeError("process_executor_result unavailable")

            bridge_out = process_executor_result(sample_blob, user_prompt="demo")
            bridge_ok = bool(
                bridge_out
                and bridge_out.run_id
                and Path(bridge_out.result_json_path).exists()
                and isinstance(bridge_out.audit.issues, list)
                and isinstance(bridge_out.ui_payload, dict)
                and all(
                    key in bridge_out.ui_payload
                    for key in ["header", "cta", "issues_by_type", "gallery", "artifacts"]
                )
            )
            checklist.append(("Reporter -> Bridge UI payload", bridge_ok, ""))

    except Exception as exc:  # pragma: no cover
        checklist.append(("Pipeline execution", False, str(exc)))

    # Checklist output
    check_lines = [
        f"{label}: {'OK' if ok else 'FAIL'}{(' — ' + note) if (note and not ok) else ''}"
        for label, ok, note in checklist
    ]
    _print_section("PIPELINE CHECKLIST", check_lines)

    # Determine gaps and readiness
    gaps: List[str] = []
    loop_path = PROJECT_ROOT / "tool" / "orchestrator" / "loop.py"
    loop_source = _read_text(loop_path)
    if "def main_loop" in loop_source:
        snippet = loop_source.split("def main_loop", 1)[1]
        body = snippet.split("def ", 1)[0] if "def " in snippet else snippet
        if "pass" in body:
            gaps.append("Orchestrator main_loop still marked as pass")

    all_ok = all(ok for label, ok, _ in checklist if label != "Pipeline execution")
    demo_ready = all_ok and bridge_out is not None

    overview_lines = [
        "Executor -> Adapter -> Aggregator -> Reporter -> Bridge -> Frontend payload",
        "Env vars: OPENROUTER_API_KEY, OPENROUTER_MODEL (loaded via dotenv where present)",
        f"Gaps: {', '.join(gaps) if gaps else 'none'}",
        f"DEMO READINESS: {'YES' if demo_ready else 'NO'}",
    ]
    if demo_ready:
        overview_lines.append("Reproduce: python scripts/audit_connectivity.py")
    else:
        overview_lines.append("Reproduce after resolving gaps: python scripts/audit_connectivity.py")
    _print_section("SYSTEM OVERVIEW", overview_lines)

    # README snippet to stdout
    readme_lines = [
        "How to run the auditor:",
        "  python scripts/audit_connectivity.py",
        "How to run the bridge demo on executor JSON:",
        "  python examples/bridge_demo.py <executor_json_path> [user_prompt]",
        "Frontend should read results from:",
        "  runs/<run_id>/result.json and runs/<run_id>/ui.json",
    ]
    _print_section("README", readme_lines)

    if not demo_ready:
        reason = next((note for label, ok, note in checklist if not ok and note), "connectivity issues")
        print(f"Audit FAILED: {reason}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
