"""FastAPI server exposing the executor actions."""

from __future__ import annotations

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


@app.post("/execute")
async def execute(req: ExecRequest):
    run_id = utils.new_run_id()
    utils.append_log(run_id, "request", req.model_dump(mode="json"))

    browser = None
    page = None
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False, slow_mo=500)
            page = await browser.new_page()
            page.set_default_timeout(5000)  # 5s per Playwright op

            await page.goto(str(req.url), timeout=10_000)

            selector_wait_error: Optional[str] = None
            try:
                await actions.wait_for_selector(page, req.selector, state="visible")
            except ValueError as exc:
                selector_wait_error = str(exc)
                errors.append(selector_wait_error)

            before_path = await actions.screenshot(page, run_id, f"step-{req.step}-before")

            for call in req.actions:
                action_fn = getattr(actions, call.fn, None)
                if action_fn is None:
                    msg = f"Unknown action: {call.fn}"
                    results.append({"fn": call.fn, "ok": False, "error": msg})
                    errors.append(msg)
                    continue

                try:
                    response = await action_fn(page, **call.args)
                    results.append({"fn": call.fn, "ok": True, "res": response})
                except (PlaywrightTimeout, PlaywrightError, Exception) as exc:
                    msg = f"Action {call.fn} failed: {exc}"
                    results.append({"fn": call.fn, "ok": False, "error": str(exc)})
                    errors.append(msg)

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
            }

            utils.append_log(run_id, "observation", observation)

            return {"run_id": run_id, "results": results, "observation": observation}

    except PlaywrightError as err:
        raise HTTPException(status_code=500, detail=f"Playwright error: {err}") from err
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
