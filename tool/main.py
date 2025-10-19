# tool/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from pathlib import Path
import json
import asyncio
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

app = FastAPI(title="ProbeTool API")

# ---------- MODEL / CLIENT INITIALIZATION ----------
# Gemini Computer Use client (single global)
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_client = genai.Client(model="gemini-2.5-pro-exp")

# OpenRouter client (single global)
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
    step: int = 0
    message: str = "starting..."
    errors: list = []

class RunResult(BaseModel):
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
@app.post("/runs")
async def start_run(request: TaskRequest):
    run_id = str(uuid4())
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(exist_ok=True)

    status = RunStatus(run_id=run_id, status="started")
    (run_dir / "status.json").write_text(status.model_dump_json())

    # --- Pipeline execution ---
    spec = await fake_openrouter_parse(request.instruction)
    observations = await fake_gemini_probe(run_id, spec)
    suggestions = await fake_suggestion_llm(observations)

    result = RunResult(
        run_id=run_id,
        success=True,
        observations=observations,
        suggestions=suggestions,
        screenshots=[obs["screenshot"] for obs in observations]
    )

    (run_dir / "result.json").write_text(result.model_dump_json())
    status.status = "completed"
    (run_dir / "status.json").write_text(status.model_dump_json())

    return {"run_id": run_id, "status": "completed"}


@app.get("/runs/{run_id}/status")
async def get_status(run_id: str):
    path = RUNS_DIR / run_id / "status.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return json.loads(path.read_text())


@app.get("/runs/{run_id}/result")
async def get_result(run_id: str):
    path = RUNS_DIR / run_id / "result.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run result not found")
    return json.loads(path.read_text())
