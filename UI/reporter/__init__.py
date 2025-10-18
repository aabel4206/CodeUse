"""Reporter package for aggregating executor run data in the CodeUse demo."""

from .gallery import build_gallery
from .io_schemas import (
    ExecutionRequest,
    ExecutionResult,
    Observation,
    ReportArtifacts,
    RunError,
    RunSummary,
)
from .run_pipeline import generate_report, load_runs
from .table import render_markdown_table

__all__ = [
    "build_gallery",
    "ExecutionRequest",
    "ExecutionResult",
    "Observation",
    "ReportArtifacts",
    "RunError",
    "RunSummary",
    "generate_report",
    "load_runs",
    "render_markdown_table",
]
