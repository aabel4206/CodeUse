"""
Typed representations for the artifacts produced by the demo executor.

The schemas are intentionally small so the rest of the reporter pipeline does
not depend on a specific storage backend. Production systems could swap these
dataclasses out for Pydantic models without touching downstream code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence


@dataclass(slots=True)
class ExecutionRequest:
    """Minimal view of what the orchestrator asked the executor to run."""

    request_id: str
    tool: str
    arguments: Sequence[str]
    cwd: str
    timeout_ms: int


@dataclass(slots=True)
class ExecutionResult:
    """Outcome metadata relayed back from the executor."""

    status: str
    exit_code: int
    duration_ms: int
    started_at: datetime
    finished_at: datetime
    highlights: List[str] = field(default_factory=list)
    observations: List["Observation"] = field(default_factory=list)
    errors: List["RunError"] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000

    @property
    def observation_count(self) -> int:
        return len(self.observations)

    @property
    def error_count(self) -> int:
        return len(self.errors)


@dataclass(slots=True)
class Observation:
    """User-facing findings gathered during the run."""

    message: str
    selector: Optional[str] = None
    severity: str = "info"
    description: Optional[str] = None
    screenshot: Optional[str] = None
    suggested_prompt: Optional[str] = None

    @classmethod
    def from_dict(cls, data: object) -> "Observation":
        if not isinstance(data, dict):
            return cls(message=str(data))
        screenshot = data.get("screenshot")
        if isinstance(screenshot, str) and screenshot.startswith("runs/"):
            screenshot = screenshot[len("runs/") :]
        return cls(
            message=str(data.get("message", "")),
            selector=data.get("selector"),
            severity=str(data.get("severity", "info")),
            description=str(data.get("description")) if data.get("description") else None,
            screenshot=screenshot,
            suggested_prompt=str(data.get("suggested_prompt"))
            if data.get("suggested_prompt")
            else (
                str(data.get("prompt")) if data.get("prompt") else None
            ),
        )


@dataclass(slots=True)
class RunError:
    """Structured error surfaced by the run."""

    message: str
    code: Optional[str] = None

    @classmethod
    def from_dict(cls, data: object) -> "RunError":
        if not isinstance(data, dict):
            return cls(message=str(data))
        return cls(
            message=str(data.get("message", "")),
            code=data.get("code"),
        )


@dataclass(slots=True)
class RunSummary:
    """Flattened record used by the reporter and CLI demo."""

    run_id: str
    created_at: datetime
    request: ExecutionRequest
    result: ExecutionResult
    artifacts: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    instruction: Optional[str] = None
    next_prompt: Optional[str] = None
    description: Optional[str] = None
    primary_screenshot: Optional[str] = None
    screenshots: List[str] = field(default_factory=list)

    @property
    def headline(self) -> str:
        return f"{self.request.tool} ({self.result.status})"


@dataclass(slots=True)
class ReportArtifacts:
    """Assets produced by rendering the reporter pipeline."""

    table_markdown: str
    gallery_html: str
