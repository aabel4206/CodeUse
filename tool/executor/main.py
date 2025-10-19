"""FastAPI server exposing the executor actions."""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from playwright.async_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

from . import actions, utils

app = FastAPI(title="Executor Service", version="0.1.0")


class ActionCall(BaseModel):
    fn: str = Field(..., description="Name of the action function to invoke.")
    args: Dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments for the action."
    )


class ExecRequest(BaseModel):
    url: HttpUrl
    actions: List[ActionCall] = Field(default_factory=list)
    selector: str = Field(..., min_length=1)
    step: int = Field(1, ge=1)
    measure_hover: bool = True
    slow_ms: int = 0


def _format_console_message(msg) -> Dict[str, Any]:
    """Serialize Playwright ConsoleMessage objects safely."""
    def _get(attr: str):
        value = getattr(msg, attr, None)
        try:
            return value() if callable(value) else value
        except Exception:
            return None

    payload: Dict[str, Any] = {
        "type": _get("type"),
        "text": _get("text"),
    }
    location = _get("location")
    if isinstance(location, dict):
        payload["location"] = location
    args = _get("args")
    if isinstance(args, list):
        try:
            payload["args"] = [str(arg) for arg in args]
        except Exception:
            pass
    return payload


@app.post("/execute")
async def execute(req: ExecRequest):
    run_id = utils.new_run_id()
    utils.append_log(run_id, "request", req.model_dump(mode="json"))

    browser = None
    context = None
    page = None
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=False,
                slow_mo=max(req.slow_ms, 0),
            )
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(5000)  # 5s per Playwright op

            console_lines: List[Dict[str, Any]] = []
            page.on("console", lambda msg: console_lines.append(_format_console_message(msg)))

            await page.goto(str(req.url), timeout=10_000)
            results.append(
                {"fn": "goto", "ok": True, "res": {"url": await actions.current_url(page)}}
            )

            selector_wait_error: Optional[str] = None
            try:
                await actions.wait_for_selector(page, req.selector, state="visible")
            except ValueError as exc:
                selector_wait_error = str(exc)
                errors.append(selector_wait_error)

            before_path = await actions.screenshot(page, run_id, f"step-{req.step}-before")
            results[-1]["screenshot"] = before_path

            link_probes: List[Dict[str, Any]] = []
            dom_scan: Optional[Dict[str, Any]] = None
            overlaps_info: List[Dict[str, Any]] = []
            bbox_info: Optional[Dict[str, Any]] = None

            for index, call in enumerate(req.actions, start=1):
                action_fn = getattr(actions, call.fn, None)
                if action_fn is None:
                    msg = f"Unknown action: {call.fn}"
                    errors.append(msg)
                    label = f"step-{req.step}-action-{index}-{call.fn}"
                    screenshot_path = await actions.screenshot(page, run_id, label)
                    results.append(
                        {"fn": call.fn, "ok": False, "error": msg, "screenshot": screenshot_path}
                    )
                    continue

                call_kwargs = dict(call.args or {})
                param_names = [param.name for param in inspect.signature(action_fn).parameters.values()]
                if "run_id" in param_names and "run_id" not in call_kwargs:
                    call_kwargs["run_id"] = run_id
                if "context" in param_names and "context" not in call_kwargs:
                    call_kwargs["context"] = context

                try:
                    if param_names and param_names[0] == "context":
                        context_arg = call_kwargs.pop("context", context)
                        response = await action_fn(context_arg, **call_kwargs)
                    elif param_names and param_names[0] == "page":
                        response = await action_fn(page, **call_kwargs)
                    else:
                        response = await action_fn(**call_kwargs)
                    entry: Dict[str, Any] = {"fn": call.fn, "ok": True, "res": response}
                except (PlaywrightTimeout, PlaywrightError, Exception) as exc:
                    msg = f"Action {call.fn} failed: {exc}"
                    errors.append(msg)
                    entry = {"fn": call.fn, "ok": False, "error": str(exc)}
                    response = {}

                label = f"step-{req.step}-action-{index}-{call.fn}"
                screenshot_path = await actions.screenshot(page, run_id, label)
                entry["screenshot"] = screenshot_path
                results.append(entry)

                if entry.get("ok"):
                    res_payload = entry.get("res") or {}
                    if call.fn == "scan_links":
                        link_probes.extend(res_payload.get("links", []))
                    elif call.fn == "scan_images":
                        dom_scan = res_payload
                    elif call.fn in {"measure_target", "get_bounding_client_rect"}:
                        bbox_info = res_payload.get("bbox") or res_payload
                    elif call.fn == "detect_overlap":
                        overlaps_info = res_payload.get("overlaps") or res_payload or []

            metrics: Dict[str, Any] = {}
            if selector_wait_error is None:
                if req.measure_hover:
                    metrics = await actions.measure_hover_metrics(page, req.selector)
                else:
                    metrics = {
                        "before": await actions.get_computed_style(page, req.selector, ""),
                        "after": await actions.get_computed_style(page, req.selector, ":hover"),
                    }
            else:
                metrics = {"selector_error": selector_wait_error}

            if bbox_info:
                metrics.setdefault("bbox", bbox_info)
            if overlaps_info:
                metrics.setdefault("overlaps", overlaps_info)

            after_path = await actions.screenshot(page, run_id, f"step-{req.step}-after")

            observation = {
                "selector": req.selector,
                "metrics": metrics,
                "screenshots": {
                    "before": before_path,
                    "after": after_path,
                },
                "screenshot": after_path,
                "url": await actions.current_url(page),
                "errors": errors,
                "console": console_lines,
            }
            if link_probes:
                observation["link_probes"] = link_probes
            if dom_scan:
                observation["dom_scan"] = dom_scan
            if overlaps_info:
                observation["overlaps"] = overlaps_info

            utils.append_log(run_id, "observation", observation)

            response_payload: Dict[str, Any] = {
                "run_id": run_id,
                "results": results,
                "observation": observation,
            }
            if console_lines:
                response_payload["console"] = console_lines
            if link_probes:
                response_payload["link_probes"] = link_probes
                response_payload["links"] = link_probes
            if dom_scan:
                response_payload["dom_scan"] = dom_scan

            return response_payload

    except PlaywrightError as err:
        raise HTTPException(status_code=500, detail=f"Playwright error: {err}") from err
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
