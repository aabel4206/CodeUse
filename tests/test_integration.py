import json
from pathlib import Path

import httpx
import pytest

from tool.orchestrator.loop import run_task


class DummyModels:
    def generate_content(self, *args, **kwargs):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"function_call": {"name": "hover_primary"}},
                            {"function_call": {"name": "take_screenshot"}},
                        ]
                    }
                }
            ]
        }


class DummyGeminiClient:
    def __init__(self):
        self.models = DummyModels()


@pytest.mark.asyncio
async def test_executor_endpoint_contract(executor_server_url: str, test_page_url: str):
    payload = {
        "url": test_page_url,
        "actions": [{"fn": "hover", "args": {"selector": "#btn1"}}],
        "selector": "#btn1",
        "step": 1,
        "measure_hover": True,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{executor_server_url}/execute", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["results"][0]["ok"] is True

    observation = data["observation"]
    assert observation["url"].startswith("http://127.0.0.1")
    assert "before" in observation["metrics"]
    assert Path(observation["screenshot"]).exists()


@pytest.mark.asyncio
async def test_run_task_success(executor_server_url: str, test_page_url: str):
    spec = {
        "target_url": test_page_url,
        "target_selector": "#btn1",
        "instruction": "Check if the first button responds to hover",
    }

    result = await run_task(spec, DummyGeminiClient(), executor_server_url)
    assert result["success"] is True
    run_id = result["run_id"]

    run_dir = Path("tool", "runs", run_id)
    assert (run_dir / "result.json").exists()
    assert "audit" in result
    assert "issues" in result["audit"]
    assert result["audit"].get("summary")
