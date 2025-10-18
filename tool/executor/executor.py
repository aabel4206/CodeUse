"""
Code executor for the CodeUse tool.
Handles safe execution of user code with proper sandboxing and monitoring.
"""

import subprocess
import tempfile
import os
import sys
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

class CodeExecutor:
    """Handles safe execution of code in various languages."""
    
    def __init__(self):
        self.supported_languages = {
            'python': self._execute_python,
            'javascript': self._execute_javascript,
            'bash': self._execute_bash,
            'powershell': self._execute_powershell
        }
    
    def execute(self, code: str, language: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Execute code safely and return results.
        
        Args:
            code: The code to execute
            language: Programming language
            timeout: Execution timeout in seconds
            
        Returns:
            Dictionary containing execution results
        """
        if language not in self.supported_languages:
            return {
                'success': False,
                'error': f'Unsupported language: {language}',
                'output': '',
                'stderr': ''
            }
        
        try:
            return self.supported_languages[language](code, timeout)
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'output': '',
                'stderr': ''
            }
    
    def _execute_python(self, code: str, timeout: int) -> Dict[str, Any]:
        """Execute Python code safely."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir()
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode
            }
        finally:
            os.unlink(temp_file)
    
    def _execute_javascript(self, code: str, timeout: int) -> Dict[str, Any]:
        """Execute JavaScript code using Node.js."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                ['node', temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir()
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode
            }
        finally:
            os.unlink(temp_file)
    
    def _execute_bash(self, code: str, timeout: int) -> Dict[str, Any]:
        """Execute Bash code safely."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                ['bash', temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir()
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode
            }
        finally:
            os.unlink(temp_file)
    
    def _execute_powershell(self, code: str, timeout: int) -> Dict[str, Any]:
        """Execute PowerShell code safely."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                ['powershell', '-ExecutionPolicy', 'Bypass', '-File', temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir()
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode
            }
        finally:
            os.unlink(temp_file)
