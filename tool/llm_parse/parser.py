"""
LLM-based code parser for the CodeUse tool.
Handles code analysis, understanding, and transformation using language models.
"""

import ast
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class CodeAnalysis:
    """Represents the analysis results of a code snippet."""
    language: str
    functions: List[Dict[str, Any]]
    classes: List[Dict[str, Any]]
    imports: List[str]
    variables: List[Dict[str, Any]]
    complexity_score: int
    potential_issues: List[str]
    suggestions: List[str]

class LLMParser:
    """Handles code parsing and analysis using LLM capabilities."""
    
    def __init__(self):
        self.supported_languages = ['python', 'javascript', 'java', 'cpp', 'c']
    
    def parse_code(self, code: str, language: str) -> CodeAnalysis:
        """
        Parse and analyze code to extract structure and insights.
        
        Args:
            code: The code to analyze
            language: Programming language
            
        Returns:
            CodeAnalysis object with parsed information
        """
        if language not in self.supported_languages:
            raise ValueError(f"Unsupported language: {language}")
        
        if language == 'python':
            return self._parse_python(code)
        else:
            return self._parse_generic(code, language)
    
    def _parse_python(self, code: str) -> CodeAnalysis:
        """Parse Python code using AST."""
        try:
            tree = ast.parse(code)
            
            functions = []
            classes = []
            imports = []
            variables = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append({
                        'name': node.name,
                        'args': [arg.arg for arg in node.args.args],
                        'line_number': node.lineno,
                        'docstring': ast.get_docstring(node)
                    })
                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        'name': node.name,
                        'bases': [base.id if hasattr(base, 'id') else str(base) for base in node.bases],
                        'line_number': node.lineno,
                        'docstring': ast.get_docstring(node)
                    })
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        imports.extend([alias.name for alias in node.names])
                    else:
                        imports.extend([f"{node.module}.{alias.name}" for alias in node.names])
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            variables.append({
                                'name': target.id,
                                'line_number': node.lineno
                            })
            
            # Calculate complexity (simplified)
            complexity = len(functions) + len(classes) * 2
            
            # Basic issue detection
            issues = self._detect_python_issues(code)
            suggestions = self._generate_suggestions(functions, classes, issues)
            
            return CodeAnalysis(
                language='python',
                functions=functions,
                classes=classes,
                imports=imports,
                variables=variables,
                complexity_score=complexity,
                potential_issues=issues,
                suggestions=suggestions
            )
            
        except SyntaxError as e:
            return CodeAnalysis(
                language='python',
                functions=[],
                classes=[],
                imports=[],
                variables=[],
                complexity_score=0,
                potential_issues=[f"Syntax error: {e}"],
                suggestions=["Fix syntax errors before analysis"]
            )
    
    def _parse_generic(self, code: str, language: str) -> CodeAnalysis:
        """Parse code for non-Python languages using regex patterns."""
        functions = []
        classes = []
        imports = []
        variables = []
        
        lines = code.split('\n')
        
        # Language-specific patterns
        if language == 'javascript':
            functions = self._extract_js_functions(code)
            imports = self._extract_js_imports(code)
        elif language in ['java', 'cpp', 'c']:
            functions = self._extract_c_functions(code)
            imports = self._extract_c_includes(code)
        
        complexity = len(functions) + len(classes) * 2
        issues = self._detect_generic_issues(code, language)
        suggestions = self._generate_suggestions(functions, classes, issues)
        
        return CodeAnalysis(
            language=language,
            functions=functions,
            classes=classes,
            imports=imports,
            variables=variables,
            complexity_score=complexity,
            potential_issues=issues,
            suggestions=suggestions
        )
    
    def _extract_js_functions(self, code: str) -> List[Dict[str, Any]]:
        """Extract JavaScript functions."""
        functions = []
        # Simple regex for function extraction
        pattern = r'function\s+(\w+)\s*\([^)]*\)'
        for match in re.finditer(pattern, code):
            functions.append({
                'name': match.group(1),
                'line_number': code[:match.start()].count('\n') + 1
            })
        return functions
    
    def _extract_js_imports(self, code: str) -> List[str]:
        """Extract JavaScript imports."""
        imports = []
        # ES6 imports
        pattern = r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]'
        imports.extend(re.findall(pattern, code))
        # CommonJS requires
        pattern = r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        imports.extend(re.findall(pattern, code))
        return imports
    
    def _extract_c_functions(self, code: str) -> List[Dict[str, Any]]:
        """Extract C/C++/Java functions."""
        functions = []
        # Simple regex for function extraction
        pattern = r'(\w+)\s+\w+\s*\([^)]*\)\s*\{'
        for match in re.finditer(pattern, code):
            functions.append({
                'name': match.group(1),
                'line_number': code[:match.start()].count('\n') + 1
            })
        return functions
    
    def _extract_c_includes(self, code: str) -> List[str]:
        """Extract C/C++ includes."""
        pattern = r'#include\s*[<"]([^>"]+)[>"]'
        return re.findall(pattern, code)
    
    def _detect_python_issues(self, code: str) -> List[str]:
        """Detect potential issues in Python code."""
        issues = []
        
        # Check for common issues
        if 'eval(' in code:
            issues.append("Use of eval() is potentially dangerous")
        if 'exec(' in code:
            issues.append("Use of exec() is potentially dangerous")
        if 'import os' in code and 'os.system' in code:
            issues.append("Direct system calls detected")
        
        return issues
    
    def _detect_generic_issues(self, code: str, language: str) -> List[str]:
        """Detect potential issues in generic code."""
        issues = []
        
        if language == 'javascript':
            if 'eval(' in code:
                issues.append("Use of eval() is potentially dangerous")
            if 'innerHTML' in code:
                issues.append("Direct innerHTML manipulation may be unsafe")
        
        return issues
    
    def _generate_suggestions(self, functions: List, classes: List, issues: List[str]) -> List[str]:
        """Generate improvement suggestions."""
        suggestions = []
        
        if len(functions) > 10:
            suggestions.append("Consider breaking down large functions into smaller ones")
        if len(classes) == 0 and len(functions) > 5:
            suggestions.append("Consider organizing code into classes")
        if issues:
            suggestions.append("Address security and safety concerns")
        
        return suggestions
