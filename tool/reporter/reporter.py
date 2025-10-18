"""
Report generator for the CodeUse tool.
Handles creation of comprehensive reports from analysis and execution results.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

class ReportGenerator:
    """Generates comprehensive reports from tool execution."""
    
    def __init__(self, output_dir: str = "runs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def generate_report(self, 
                       run_id: str,
                       analysis_results: Dict[str, Any],
                       execution_results: Dict[str, Any],
                       metadata: Dict[str, Any]) -> str:
        """
        Generate a comprehensive report for a run.
        
        Args:
            run_id: Unique identifier for the run
            analysis_results: Results from code analysis
            execution_results: Results from code execution
            metadata: Additional metadata about the run
            
        Returns:
            Path to the generated report file
        """
        report_data = {
            'run_id': run_id,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata,
            'analysis': analysis_results,
            'execution': execution_results,
            'summary': self._generate_summary(analysis_results, execution_results)
        }
        
        # Generate different report formats
        json_report = self._generate_json_report(report_data, run_id)
        markdown_report = self._generate_markdown_report(report_data, run_id)
        
        return json_report  # Return JSON report path as primary
    
    def _generate_json_report(self, report_data: Dict[str, Any], run_id: str) -> str:
        """Generate JSON format report."""
        report_path = self.output_dir / f"{run_id}_report.json"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        return str(report_path)
    
    def _generate_markdown_report(self, report_data: Dict[str, Any], run_id: str) -> str:
        """Generate Markdown format report."""
        report_path = self.output_dir / f"{run_id}_report.md"
        
        markdown_content = self._format_markdown_report(report_data)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        return str(report_path)
    
    def _format_markdown_report(self, report_data: Dict[str, Any]) -> str:
        """Format report data as Markdown."""
        content = []
        
        # Header
        content.append(f"# CodeUse Analysis Report")
        content.append(f"**Run ID:** {report_data['run_id']}")
        content.append(f"**Timestamp:** {report_data['timestamp']}")
        content.append("")
        
        # Summary
        content.append("## Summary")
        summary = report_data['summary']
        content.append(f"- **Status:** {summary['status']}")
        content.append(f"- **Language:** {summary['language']}")
        content.append(f"- **Complexity Score:** {summary['complexity_score']}")
        content.append(f"- **Functions Found:** {summary['function_count']}")
        content.append(f"- **Classes Found:** {summary['class_count']}")
        content.append(f"- **Issues Detected:** {summary['issue_count']}")
        content.append("")
        
        # Analysis Results
        if 'analysis' in report_data:
            content.append("## Code Analysis")
            analysis = report_data['analysis']
            
            if 'functions' in analysis and analysis['functions']:
                content.append("### Functions")
                for func in analysis['functions']:
                    content.append(f"- **{func.get('name', 'Unknown')}** (Line {func.get('line_number', '?')})")
                    if 'docstring' in func and func['docstring']:
                        content.append(f"  - {func['docstring']}")
                content.append("")
            
            if 'classes' in analysis and analysis['classes']:
                content.append("### Classes")
                for cls in analysis['classes']:
                    content.append(f"- **{cls.get('name', 'Unknown')}** (Line {cls.get('line_number', '?')})")
                    if 'docstring' in cls and cls['docstring']:
                        content.append(f"  - {cls['docstring']}")
                content.append("")
            
            if 'potential_issues' in analysis and analysis['potential_issues']:
                content.append("### Potential Issues")
                for issue in analysis['potential_issues']:
                    content.append(f"- ⚠️ {issue}")
                content.append("")
            
            if 'suggestions' in analysis and analysis['suggestions']:
                content.append("### Suggestions")
                for suggestion in analysis['suggestions']:
                    content.append(f"- 💡 {suggestion}")
                content.append("")
        
        # Execution Results
        if 'execution' in report_data:
            content.append("## Execution Results")
            execution = report_data['execution']
            
            content.append(f"- **Success:** {'✅ Yes' if execution.get('success', False) else '❌ No'}")
            content.append(f"- **Return Code:** {execution.get('return_code', 'N/A')}")
            
            if execution.get('output'):
                content.append("### Output")
                content.append("```")
                content.append(execution['output'])
                content.append("```")
                content.append("")
            
            if execution.get('stderr'):
                content.append("### Error Output")
                content.append("```")
                content.append(execution['stderr'])
                content.append("```")
                content.append("")
        
        return "\n".join(content)
    
    def _generate_summary(self, analysis_results: Dict[str, Any], execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of the analysis and execution results."""
        summary = {
            'status': 'completed' if execution_results.get('success', False) else 'failed',
            'language': analysis_results.get('language', 'unknown'),
            'complexity_score': analysis_results.get('complexity_score', 0),
            'function_count': len(analysis_results.get('functions', [])),
            'class_count': len(analysis_results.get('classes', [])),
            'issue_count': len(analysis_results.get('potential_issues', [])),
            'suggestion_count': len(analysis_results.get('suggestions', []))
        }
        
        return summary
    
    def list_reports(self) -> List[Dict[str, Any]]:
        """List all available reports."""
        reports = []
        
        for json_file in self.output_dir.glob("*_report.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                    reports.append({
                        'run_id': report_data.get('run_id'),
                        'timestamp': report_data.get('timestamp'),
                        'status': report_data.get('summary', {}).get('status', 'unknown'),
                        'file_path': str(json_file)
                    })
            except Exception as e:
                print(f"Error reading report {json_file}: {e}")
        
        return sorted(reports, key=lambda x: x['timestamp'], reverse=True)
    
    def get_report(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific report by run ID."""
        report_path = self.output_dir / f"{run_id}_report.json"
        
        if not report_path.exists():
            return None
        
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading report {report_path}: {e}")
            return None
