"""
State management for the CodeUse tool.
This module handles the application state and data persistence.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

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
            status="running"
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
