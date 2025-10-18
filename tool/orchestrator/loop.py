"""
Main orchestration loop for the CodeUse tool.
This module handles the coordination between different components.
"""

import time
from typing import Dict, Any, List, Optional
from .state import State
from tool.orchestrator.state import ProbeEvent

# Aggregation and persistence helpers (called at end of successful runs)
from tool.reporter.aggregator import build_audit_result
from tool.reporter.reporter import write_result_json

class Orchestrator:
    """Main orchestrator class that coordinates the tool's workflow."""
    
    def __init__(self):
        self.state = State()
        self.running = False
    
    def start(self):
        """Start the main orchestration loop."""
        self.running = True
        print("Orchestrator started")
        
        while self.running:
            try:
                self.main_loop()
                time.sleep(1)  # Prevent busy waiting
            except KeyboardInterrupt:
                print("Orchestrator stopped by user")
                self.stop()
            except Exception as e:
                print(f"Error in orchestrator loop: {e}")
                # Continue running unless critical error
    
    def stop(self):
        """Stop the orchestration loop."""
        self.running = False
        print("Orchestrator stopped")
    
    def main_loop(self):
        """Main processing loop."""
        # TODO: Implement the main orchestration logic
        # This will coordinate between:
        # - LLM parsing
        # - Code execution
        # - Result reporting
        pass

    # Helper to finalize a run by aggregating results and writing audit JSON
    def finalize_successful_run(
        self,
        *,
        run_id: str,
        target_url: str,
        run_dir: str,
        cta_info: Optional[Dict[str, Any]],
        probe_events: List[ProbeEvent],
        console_lines: List[Dict[str, Any]],
        link_probes: List[Dict[str, Any]],
        dom_scan: Optional[Dict[str, Any]],
    ):
        audit = build_audit_result(
            run_id=run_id,
            target_url=target_url,
            primary_cta=cta_info,
            probe_events=probe_events,
            console_lines=console_lines,
            link_probes=link_probes,
            dom_scan=dom_scan or {},
            artifacts={
                "screenshots_dir": run_dir,
                "action_log": f"{run_dir}/actions.jsonl",
            },
        )
        write_result_json(run_dir, audit)
        return audit

def main_loop():
    """Entry point for the main orchestration loop."""
    orchestrator = Orchestrator()
    orchestrator.start()
