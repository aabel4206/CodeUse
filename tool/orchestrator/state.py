"""
State management for the CodeUse tool.
This module handles the application state and shared schemas.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

# Existing dataclass-based state (kept intact)

@dataclass
class RunState:
    """Represents the state of a single run."""
    run_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


class State:
    """Main state manager for the application."""

    def __init__(self):
        self.current_run: Optional[RunState] = None
        self.run_history: Dict[str, RunState] = {}
        self.config: Dict[str, Any] = {}

    def start_run(self, run_id: str, input_data: Dict[str, Any]) -> RunState:
        """Start a new run and return its state."""
        run_state = RunState(
            run_id=run_id,
            start_time=datetime.now(),
            input_data=input_data,
            status="running",
        )
        self.current_run = run_state
        self.run_history[run_id] = run_state
        return run_state

    def complete_run(self, run_id: str, output_data: Dict[str, Any]):
        """Mark a run as completed."""
        if run_id in self.run_history:
            run_state = self.run_history[run_id]
            run_state.end_time = datetime.now()
            run_state.status = "completed"
            run_state.output_data = output_data

    def fail_run(self, run_id: str, error_message: str):
        """Mark a run as failed."""
        if run_id in self.run_history:
            run_state = self.run_history[run_id]
            run_state.end_time = datetime.now()
            run_state.status = "failed"
            run_state.error_message = error_message

    def get_run(self, run_id: str) -> Optional[RunState]:
        """Get a run by its ID."""
        return self.run_history.get(run_id)

    def get_all_runs(self) -> Dict[str, RunState]:
        """Get all runs."""
        return self.run_history.copy()


# -------------------------
# Shared Pydantic schemas
# -------------------------

from typing import Literal
from pydantic import BaseModel, Field

__all__ = [
    "PrimaryCTA",
    "ProbeEvent",
    "IssueType",
    "Issue",
    "AuditResult",
    "make_issue_id",
]


class PrimaryCTA(BaseModel):
    selector: str
    found_by: Literal["gemini_cu", "heuristic"]
    confidence: float = 0.0
    rationale: Optional[str] = None


class ProbeEvent(BaseModel):
    step: int
    action_plan: List[Dict[str, Any]] = Field(default_factory=list)
    executor_ok: bool = True
    metrics: Optional[Dict[str, Any]] = None
    screenshot: Optional[str] = None
    notes: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


IssueType = Literal[
    "hover_animation",
    "console_error",
    "broken_link",
    "missing_alt",
    "missing_accessible_name",
    "overlap",
    "small_click_target",
    "cta_not_found",
]


class Issue(BaseModel):
    id: str
    type: IssueType
    severity: Literal["low", "medium", "high"]
    selector: Optional[str] = None
    summary: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    suggested_fix: str


class AuditResult(BaseModel):
    run_id: str
    success: bool
    target_url: str
    primary_cta: Optional[PrimaryCTA] = None
    issues: List[Issue] = Field(default_factory=list)
    artifacts: Dict[str, Any]


def make_issue_id(prefix: str, n: int) -> str:
    """Create a stable, human-readable issue ID like 'hover-003'."""
    return f"{prefix}-{n:03d}"


# -------------------------
# File I/O functions for loop.py
# -------------------------

import json
from pathlib import Path


def save_observation(run_dir: Path, step: int, observation: Dict[str, Any]):
    """Save an observation to a step file."""
    step_file = run_dir / f"step-{step}.json"
    step_file.write_text(json.dumps(observation, indent=2, ensure_ascii=False))


def save_result(run_dir: Path, result: Dict[str, Any]):
    """Save the final result to result.json."""
    result_file = run_dir / "result.json"
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))


def update_status(run_dir: Path, status: Dict[str, Any]):
    """Update the status.json file."""
    status_file = run_dir / "status.json"
    status_file.write_text(json.dumps(status, indent=2, ensure_ascii=False))
