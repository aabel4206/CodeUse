"""FastAPI server exposing the executor actions."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, Error as PlaywrightError

from . import actions, utils

app = FastAPI(title="Executor Service", version="0.1.0")


class ActionCall(BaseModel):
    fn: str = Field(..., description="Name of the action function to invoke.")
    args: Dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments for the action."
    )


class ExecRequest(BaseModel):
    url: str
    actions: List[ActionCall]
    selector: str
    step: int


@app.post("/execute")
async def execute(req: ExecRequest):
    run_id = utils.new_run_id()

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(req.url)

            results = []
            for action_call in req.actions:
                action_fn = getattr(actions, action_call.fn, None)
                if action_fn is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unknown action: {action_call.fn}",
                    )

                response = await action_fn(page, **action_call.args)
                results.append({"fn": action_call.fn, "result": response})

            metrics = await actions.get_computed_style(page, req.selector)
            screenshot_path = await actions.screenshot(
                page, f"{run_id}-step{req.step}"
            )

            await browser.close()
    except PlaywrightError as err:
        raise HTTPException(
            status_code=500, detail=f"Playwright error: {err}"
        ) from err

    observation = {
        "metrics": metrics,
        "screenshot": screenshot_path,
        "errors": [],
    }

    return {
        "run_id": run_id,
        "results": results,
        "observation": observation,
    }
