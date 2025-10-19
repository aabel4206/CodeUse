from pathlib import Path

import pytest

from tool.executor.main import ExecRequest, execute_request
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
async def test_executor_direct_call(test_page_url: str):
    payload = {
        "url": test_page_url,
        "actions": [{"fn": "hover", "args": {"selector": "[data-testid='btn-campaign']"}}],
        "selector": "[data-testid='btn-campaign']",
        "step": 1,
        "measure_hover": True,
    }

    request = ExecRequest.model_validate(payload)
    data = await execute_request(request)

    assert "run_id" in data
    assert data["results"][0]["ok"] is True

    observation = data["observation"]
    assert observation["url"].startswith("http://127.0.0.1")
    assert "before" in observation["metrics"]
    assert Path(observation["screenshot"]).exists()


@pytest.mark.asyncio
async def test_run_task_success(test_page_url: str):
    spec = {
        "target_url": test_page_url,
        "target_selector": "[data-testid='btn-campaign']",
        "instruction": "Check if the first button responds to hover",
    }

    result = await run_task(spec, DummyGeminiClient())
    assert result["success"] is True
    run_id = result["run_id"]

    run_dir = Path("tool", "runs", run_id)
    assert (run_dir / "result.json").exists()
    assert "audit" in result
    assert "issues" in result["audit"]
    assert result["audit"].get("summary")
