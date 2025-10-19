"""Executor utilities for CodeUse.

This module still exposes the original code-execution helpers and now also
provides a Playwright-based ``run_audit`` helper used by the demo CLI.
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

from . import actions, utils

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


# ---------------------------------------------------------------------------
# Playwright audit helper (Role C demo)
# ---------------------------------------------------------------------------


def _safe_console_message(msg):
    """Normalize Playwright ConsoleMessage for serialisation."""

    def get(attr):
        value = getattr(msg, attr, None)
        try:
            return value() if callable(value) else value
        except Exception:
            return None

    out = {
        "type": get("type"),
        "text": get("text"),
    }
    loc = get("location")
    if isinstance(loc, dict):
        out["location"] = loc
    args = get("args")
    if isinstance(args, list):
        try:
            out["args"] = [str(a) for a in args]
        except Exception:
            pass
    return out


async def _collect_links(page) -> List[Dict[str, Any]]:
    links = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
            href: a.getAttribute('href'),
            url: a.href
        }))
        """
    )
    probes: List[Dict[str, Any]] = []
    for item in links:
        url = item.get("url")
        status = 0
        try:
            if url:
                response = await page.request.get(url)
                status = response.status
        except Exception:
            status = 0
        probes.append({"href": item.get("href"), "url": url, "status": status})
    return probes


async def _collect_dom_scan(page) -> Dict[str, Any]:
    return await page.evaluate(
        r"""
        () => {
            const summarize = (el) => {
                if (!el) return 'unknown';
                const id = el.id ? `#${el.id}` : '';
                const classes = (el.className && typeof el.className === 'string')
                    ? '.' + el.className.trim().split(/\s+/).filter(Boolean).join('.')
                    : '';
                const tag = el.tagName ? el.tagName.toLowerCase() : 'node';
                const label = (tag + id + classes).trim();
                return label || tag;
            };

            const missingAlt = Array.from(document.querySelectorAll('img')).filter(
                img => !(img.getAttribute('alt') || '').trim()
            );

            const clickableSelectors = Array.from(document.querySelectorAll(
                'button, a, [role="button"], [tabindex]'
            ));
            const withoutName = clickableSelectors.filter(el => {
                const hasText = (el.innerText || '').trim().length > 0;
                const hasAria = (el.getAttribute('aria-label') || '').trim().length > 0;
                return !(hasText || hasAria);
            }).map(summarize);

            return {
                img_missing_alt_count: missingAlt.length,
                clickables_without_name: withoutName,
            };
        }
        """
    )


async def _collect_overlaps(page, selector: str) -> List[Dict[str, Any]]:
    return await page.evaluate(
        r"""
        (sel) => {
            const el = document.querySelector(sel);
            if (!el) return [];
            const rect = el.getBoundingClientRect();
            if (!rect) return [];
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            const topEl = document.elementFromPoint(centerX, centerY);
            if (topEl && topEl !== el) {
                const id = topEl.id ? `#${topEl.id}` : '';
                const classes = (topEl.className && typeof topEl.className === 'string')
                    ? '.' + topEl.className.trim().split(/\s+/).filter(Boolean).join('.')
                    : '';
                const tag = topEl.tagName ? topEl.tagName.toLowerCase() : 'node';
                const selectorHint = (tag + id + classes).trim() || tag;
                return [{"selector": selectorHint}];
            }
            return [];
        }
        """,
        selector,
    )


async def _run_audit_async(
    target_url: str,
    run_id: Optional[str] = None,
    *,
    slow_ms: int = 0,
    selector: str = "#btn1",
) -> Dict[str, Any]:
    slow_ms = int(slow_ms or 0)

    run_id = run_id or utils.new_run_id()
    console_lines: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False,
            slow_mo=slow_ms if slow_ms > 0 else 0,
        )
        context = await browser.new_context()
        page = await context.new_page()

        page.on("console", lambda msg: console_lines.append(_safe_console_message(msg)))

        async def _maybe_pause():
            if slow_ms > 0:
                try:
                    await page.wait_for_timeout(slow_ms)
                except Exception:
                    pass

        try:
            await page.goto(target_url, timeout=15_000)
            results.append({"fn": "goto", "ok": True, "res": {"url": page.url}})
            await _maybe_pause()

            before_path = await actions.screenshot(page, run_id, "step-1-before")
            results.append({"fn": "screenshot", "ok": True, "res": {"path": before_path, "label": "before"}})
            await _maybe_pause()

            metrics = await actions.measure_hover_metrics(page, selector, slow_ms=slow_ms)
            bbox = await actions.get_bounding_client_rect(page, selector)
            overlaps = await _collect_overlaps(page, selector)

            metrics.update({
                "bbox": bbox,
                "overlaps": overlaps,
                "url": page.url,
            })
            results.append({"fn": "measure_hover_metrics", "ok": True, "res": metrics})
            await _maybe_pause()

            after_path = await actions.screenshot(page, run_id, "step-1-after")
            results.append({"fn": "screenshot", "ok": True, "res": {"path": after_path, "label": "after"}})

            link_probes = await _collect_links(page)
            dom_scan = await _collect_dom_scan(page)

            observation = {
                "selector": selector,
                "metrics": metrics,
                "screenshots": [
                    {"label": "before", "path": before_path},
                    {"label": "after", "path": after_path},
                ],
                "screenshot": after_path,
                "url": page.url,
                "errors": errors,
            }

            return {
                "run_id": run_id,
                "results": results,
                "observation": observation,
                "console": console_lines,
                "links": link_probes,
                "dom_scan": dom_scan,
            }

        except (PlaywrightTimeout, PlaywrightError) as exc:
            errors.append(str(exc))
            return {
                "run_id": run_id,
                "results": results,
                "observation": {
                    "selector": selector,
                    "metrics": {},
                    "screenshots": [],
                    "screenshot": None,
                    "url": target_url,
                    "errors": errors,
                },
                "console": console_lines,
                "links": [],
                "dom_scan": {},
            }
        finally:
            await page.close()
            await context.close()
            await browser.close()


def run_audit(
    target_url: str,
    run_id: Optional[str] = None,
    *,
    slow_ms: int = 0,
) -> Dict[str, Any]:
    """Run the Playwright executor with optional slow motion."""

    if not target_url:
        raise ValueError("target_url is required")

    return asyncio.run(
        _run_audit_async(target_url=target_url, run_id=run_id, slow_ms=slow_ms)
    )
    
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
