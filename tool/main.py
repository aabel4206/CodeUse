# tool/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from pathlib import Path
import json
import os

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from orchestrator.loop import run_task
from llm_parse.parser import OpenRouterParser
from google import genai  # Gemini SDK

from tool.cli import CLIGeminiClient, _functions_for_mode, _infer_mode
from tool.orchestrator.loop import run_task

app = FastAPI(title="ProbeTool API")

# ---------- MODEL / CLIENT INITIALIZATION ----------
# Gemini Computer Use client (single global)
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_client = genai.Client(model="gemini-2.5-pro-exp")

# OpenRouter client (single global)
# OpenRouter client (single global) – currently unused but kept for future wiring.
from openai import OpenAI
openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

RUNS_DIR = Path(__file__).parent / "runs"
RUNS_DIR.mkdir(exist_ok=True)

# -------------------------------
# MODELS
# -------------------------------
class TaskRequest(BaseModel):
    instruction: str = "probe around the website to find errors or suggest improvements"
    target_url: str = os.getenv("DEFAULT_TARGET_URL", "http://localhost:5173")

class RunStatus(BaseModel):
    run_id: str
    status: str
    step: int | None = None
    success: bool | None = None
    message: str | None = None
    errors: list | None = None


class RunStartResponse(BaseModel):
    run_id: str
    success: bool
    observations: list
    suggestions: list
    screenshots: list


# -------------------------------
# HELPERS
# -------------------------------
async def fake_openrouter_parse(instruction: str):
    # Simulate parsing with OpenRouter
    await asyncio.sleep(0.5)
    return {
        "target_url": os.getenv("DEFAULT_TARGET_URL", "http://localhost:5173"),
        "goals": ["discover UI issues", "find broken links", "check layout consistency"],
        "max_steps": 3
    }

async def fake_gemini_probe(run_id: str, spec: dict):
    # Simulate Gemini Computer Use probing
    results = []
    for step in range(1, spec["max_steps"] + 1):
        obs = {
            "step": step,
            "actions": [{"fn": "navigate", "args": {"url": spec["target_url"]}}],
            "screenshot": f"step-{step}.png",
            "issues_found": [
                {"type": "broken_link", "selector": "a[href='/pricingg']", "severity": "high"},
                {"type": "missing_alt", "selector": "img.hero", "severity": "medium"}
            ]
        }
        results.append(obs)
        await asyncio.sleep(1)  # simulate network delay
    return results

async def fake_suggestion_llm(observations: list):
    # Simulate suggestion generation
    await asyncio.sleep(0.5)
    return [
        {"title": "Fix broken link", "why": "404 on /pricingg", "how": "Change href to /pricing"},
        {"title": "Add missing alt text", "why": "Improves accessibility", "how": "Add alt attribute"}
    ]


# -------------------------------
# ROUTES
# -------------------------------
@app.post("/runs", response_model=RunStartResponse)
async def start_run(request: TaskRequest):
    if request.task_spec:
        spec = dict(request.task_spec)
    else:
        spec = {
            "target_url": str(request.target_url),
            "target_selector": request.target_selector,
            "instruction": request.instruction,
        }

    if gemini_client is not None:
        client = gemini_client
    else:
        mode = request.mode.lower()
        if mode == "auto":
            mode = _infer_mode(request.instruction)
        function_names = _functions_for_mode(mode)
        client = CLIGeminiClient(function_names)

    result = await run_task(spec, client)
    status = "completed" if result.get("success") else "failed"
    return RunStartResponse(
        run_id=result.get("run_id"),
        status=status,
        audit=result.get("audit"),
        errors=result.get("errors", []),
    )


@app.get("/runs/{run_id}/status", response_model=RunStatus)
async def get_status(run_id: str):
    path = RUNS_DIR / run_id / "status.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    data = json.loads(path.read_text())
    return RunStatus(
        run_id=run_id,
        status=data.get("state", data.get("status", "unknown")),
        step=data.get("step"),
        success=data.get("success"),
        message=data.get("message"),
        errors=data.get("errors"),
    )


@app.get("/runs/{run_id}/result")
async def get_result(run_id: str):
    path = RUNS_DIR / run_id / "result.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run result not found")
    return json.loads(path.read_text())
