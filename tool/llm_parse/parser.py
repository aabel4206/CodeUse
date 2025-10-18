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

# --------------------
# TaskSpec Parser (Appended)
# --------------------

# Local imports for the new functionality (kept scoped to appended section)
import os
import json
from typing import Tuple

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover - httpx might be unavailable during static scans
    httpx = None  # fallback stub; runtime checks guard usage

try:
    from pydantic import BaseModel, Field
    from typing import Literal
except Exception as _e:  # pragma: no cover
    # If pydantic is not installed at runtime, we still want import to succeed in environments
    # that only analyze code. However, execution of TaskSpec construction will naturally fail
    # without pydantic present; callers should install pydantic.
    raise _e


class TaskSpec(BaseModel):
    """Structured specification for UI tasks consumed by the orchestrator."""
    task: "Literal['ui-hover-tune','ui-assert','ui-explore','generic']" = "generic"
    target_url: Optional[str] = None
    target_selector: Optional[str] = None
    desired: Dict[str, Any] = Field(default_factory=dict)
    tolerances: Dict[str, Any] = Field(default_factory=lambda: {"scale": 0.01, "duration_ms": 15})
    max_steps: int = 12
    notes: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


def _strip_to_json(text: str) -> str:
    """Attempt to coerce model output to a clean JSON string.

    - Strips code fences like ```json ... ``` or ``` ... ```
    - If leading prose is present, extracts the first balanced JSON object/array
    """
    if not text:
        return "{}"

    s = text.strip()

    # Strip fenced code blocks
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s, flags=re.IGNORECASE)
    if fence_match:
        s = fence_match.group(1).strip()

    # Fast path: looks like JSON already
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        return s

    # Try to find the first balanced JSON object or array
    def _extract_balanced(chunk: str, open_ch: str, close_ch: str) -> Optional[str]:
        depth = 0
        start = chunk.find(open_ch)
        if start == -1:
            return None
        for i in range(start, len(chunk)):
            ch = chunk[i]
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return chunk[start : i + 1]
        return None

    obj = _extract_balanced(s, "{", "}")
    if obj:
        return obj
    arr = _extract_balanced(s, "[", "]")
    if arr:
        return arr

    # Fallback: try to locate substring that looks like a JSON object quickly
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        return m.group(0)

    return "{}"


def _regex_guess_url_and_selector(instruction: str) -> Tuple[Optional[str], Optional[str]]:
    """Heuristic extraction for URL and selector when LLM parsing fails.

    - URL: first http(s) URL
    - Selector: first CSS token like #id or .class, or a quoted value after 'selector'
    """
    if not instruction:
        return None, None

    url_match = re.search(r"https?://[^\s'\"]+", instruction)
    url = url_match.group(0) if url_match else None

    sel = None
    # Look for explicit 'selector: "..."' or selector "..."
    m = re.search(r"selector\s*[:=]\s*['\"]([^'\"]+)['\"]", instruction, flags=re.IGNORECASE)
    if m:
        sel = m.group(1).strip()
    if not sel:
        m = re.search(r"\s(['\"][#.][A-Za-z0-9_\-\[\]=:'\"\s]+['\"])", instruction)
        if m:
            sel = m.group(1).strip("'\"")
    if not sel:
        m = re.search(r"([#.][A-Za-z0-9_\-]+)", instruction)
        if m:
            sel = m.group(1)

    return url, sel


def _apply_defaults(spec: TaskSpec) -> TaskSpec:
    """Normalize and enforce safe defaults without being overly strict."""
    allowed = {"ui-hover-tune", "ui-assert", "ui-explore", "generic"}
    if spec.task not in allowed:
        spec.task = "generic"

    # max_steps sane bounds
    try:
        if not isinstance(spec.max_steps, int) or spec.max_steps <= 0:
            spec.max_steps = 12
        spec.max_steps = min(spec.max_steps, 100)
    except Exception:
        spec.max_steps = 12

    if spec.desired is None or not isinstance(spec.desired, dict):
        spec.desired = {}

    if spec.tolerances is None or not isinstance(spec.tolerances, dict):
        spec.tolerances = {"scale": 0.01, "duration_ms": 15}
    else:
        spec.tolerances.setdefault("scale", 0.01)
        spec.tolerances.setdefault("duration_ms", 15)

    # Normalize strings
    if spec.target_url:
        spec.target_url = spec.target_url.strip()
    if spec.target_selector:
        spec.target_selector = spec.target_selector.strip()
    if spec.notes:
        spec.notes = spec.notes.strip()

    return spec


class OpenRouterClient:
    """Thin client for calling OpenRouter to parse instructions into TaskSpec JSON."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        # Prefer Claude Sonnet; allow override; keep small OpenAI option as a backup default
        self.model = model or os.getenv("OPENROUTER_MODEL") or "anthropic/claude-3.5-sonnet"

    def parse_task(self, instruction: str) -> TaskSpec:
        errors: List[str] = []

        if not self.api_key:
            return TaskSpec(errors=["missing OPENROUTER_API_KEY"], notes="Skipped LLM; using fallbacks")

        if httpx is None:
            return TaskSpec(errors=["httpx not available"], notes="Skipped LLM; using fallbacks")

        system_prompt = (
            "You convert natural-language UI test/repair requests into a strict JSON TaskSpec. "
            "Output ONLY JSON complying with the provided schema. No prose."
        )

        # Inline schema example for ui-hover-tune
        example = {
            "task": "ui-hover-tune",
            "target_url": "https://example.com/profile",
            "target_selector": "#avatar",
            "desired": {"scale": 1.05, "duration_ms": 150, "timing": "ease-out"},
            "tolerances": {"scale": 0.01, "duration_ms": 15},
            "max_steps": 12,
            "notes": "Adjust hover scale and timing",
            "errors": [],
        }

        user_prompt = (
            "Instruction:\n" + instruction.strip() + "\n\n"
            "Schema fields: task, target_url, target_selector, desired, tolerances, max_steps, notes, errors.\n"
            "Example (ui-hover-tune):\n" + json.dumps(example, ensure_ascii=False)
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # Nudge JSON-only
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_REFERRER", "https://localhost"),
            "X-Title": "codeuse",
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return TaskSpec(errors=[f"openrouter error: {e}"], notes="LLM call failed; using fallbacks")

        try:
            choice0 = (data.get("choices") or [{}])[0]
            msg = choice0.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list) and content:
                # Some providers return a list of content parts
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if not isinstance(content, str):
                content = json.dumps(content or {})

            json_str = _strip_to_json(content)
            parsed = json.loads(json_str)
            if not isinstance(parsed, dict):
                parsed = {}
            return TaskSpec(**parsed)
        except Exception as e:
            return TaskSpec(errors=[f"invalid LLM JSON: {e}"], notes="LLM parse failed; using fallbacks")


def parse_instruction_to_taskspec(instruction: str) -> "TaskSpec":
    """Public API: Parse a natural-language instruction into a TaskSpec.

    This function never raises due to user input. On failure it returns a
    best-effort TaskSpec with errors populated and reasonable defaults applied.
    """
    try:
        if not instruction or not instruction.strip():
            return _apply_defaults(TaskSpec(errors=["empty instruction"]))

        client = OpenRouterClient()
        spec = client.parse_task(instruction)

        # If LLM path failed (errors populated or minimal content), fallback heuristics
        errs: List[str] = list(spec.errors or [])
        if errs or (not spec.target_url and not spec.target_selector and spec.task == "generic"):
            url, sel = _regex_guess_url_and_selector(instruction)
            # Only fill if missing to preserve any LLM-inferred fields
            if not spec.target_url:
                spec.target_url = url
            if not spec.target_selector:
                spec.target_selector = sel
            if not spec.task:
                spec.task = "generic"
            if not errs:
                errs.append("heuristic fallback applied")
            spec.errors = errs

        return _apply_defaults(spec)
    except Exception as e:
        # Last-resort guardrail — never raise to caller
        url, sel = _regex_guess_url_and_selector(instruction or "")
        fallback = TaskSpec(
            task="generic",
            target_url=url,
            target_selector=sel,
            errors=[f"unhandled error: {e}", "returned best-effort TaskSpec"],
        )
        return _apply_defaults(fallback)


if __name__ == "__main__":  # lite ad-hoc tests
    samples = [
        "Tune the hover on #cta so it scales to 1.05 and eases out on https://example.com/home",
        "Assert that the profile avatar shows tooltip on hover. selector: '#avatar' url: https://example.com/profile",
        "Open the page and explore the menu at .menu",
        "",
    ]

    for s in samples:
        spec = parse_instruction_to_taskspec(s)
        print("Instruction:", s)
        print("TaskSpec:", spec.model_dump() if hasattr(spec, "model_dump") else spec.dict())
        print("-" * 60)
