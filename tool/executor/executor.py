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
from urllib.parse import urlparse

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
    follow_one_link: bool = True,
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

        extras: Dict[str, Any] = {}

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

            try:
                await actions.click(page, selector, slow_ms=slow_ms)
                await _maybe_pause()
            except Exception as click_exc:
                errors.append(f"click parent failed: {click_exc}")

            after_path = await actions.screenshot(page, run_id, "step-1-after")
            results.append({"fn": "screenshot", "ok": True, "res": {"path": after_path, "label": "after"}})

            link_probes = await _collect_links(page)
            dom_scan = await _collect_dom_scan(page)
            dom_scan.setdefault("img_missing_alt_count", 0)
            dom_scan.setdefault("clickables_without_name", [])

            for probe in link_probes:
                probe["page"] = "parent"

            link_probes_parent_entry = {"url": page.url, "status": 200, "page": "parent"}
            link_probes.insert(0, link_probes_parent_entry)

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

            parent_origin = urlparse(page.url)
            child_data: Optional[Dict[str, Any]] = None

            child_url = None
            if follow_one_link:
                for entry in link_probes:
                    url = entry.get("url")
                    if not url:
                        continue
                    parsed = urlparse(url)
                    if parsed.scheme not in ("http", "https"):
                        continue
                    if parsed.netloc != parent_origin.netloc:
                        continue
                    if parsed.fragment:
                        continue
                    if entry.get("page") == "parent" and url == page.url:
                        continue
                    child_url = url
                    break

            if child_url:
                try:
                    await page.goto(child_url, timeout=15_000)
                    await _maybe_pause()
                    results.append({"fn": "goto", "ok": True, "res": {"url": page.url}, "context": "child"})

                    child_selector = "#btn2"
                    child_before = await actions.screenshot(page, run_id, "child-step-1-before")
                    await _maybe_pause()

                    child_metrics = {}
                    has_child_selector = await page.query_selector(child_selector)
                    if has_child_selector:
                        child_metrics = await actions.measure_hover_metrics(
                            page, child_selector, slow_ms=slow_ms
                        )
                        child_bbox = await actions.get_bounding_client_rect(page, child_selector)
                        child_overlaps = await _collect_overlaps(page, child_selector)
                        child_metrics.update(
                            {
                                "bbox": child_bbox,
                                "overlaps": child_overlaps,
                                "url": page.url,
                            }
                        )
                        results.append({
                            "fn": "measure_hover_metrics",
                            "ok": True,
                            "res": child_metrics,
                            "context": "child",
                        })
                        try:
                            await actions.click(page, child_selector, slow_ms=slow_ms)
                        except Exception as child_click_exc:
                            errors.append(f"click child failed: {child_click_exc}")
                        await _maybe_pause()
                    else:
                        child_metrics = {}

                    child_after = await actions.screenshot(page, run_id, "child-step-1-after")
                    results.append({
                        "fn": "screenshot",
                        "ok": True,
                        "res": {"path": child_after, "label": "child-after"},
                        "context": "child",
                    })

                    child_dom_scan = await _collect_dom_scan(page)
                    child_links = await _collect_links(page)
                    for probe in child_links:
                        probe["page"] = "child"
                    link_probes.append({"url": child_url, "status": 200, "page": "child"})
                    link_probes.extend(child_links)

                    dom_scan.setdefault("img_missing_alt_count", 0)
                    dom_scan["img_missing_alt_count"] += child_dom_scan.get("img_missing_alt_count", 0)
                    base_list = dom_scan.setdefault("clickables_without_name", [])
                    base_list.extend(child_dom_scan.get("clickables_without_name", []))

                    child_data = {
                        "url": child_url,
                        "selector": child_selector if has_child_selector else None,
                        "metrics": child_metrics,
                        "screenshots": {
                            "before": child_before,
                            "after": child_after,
                        },
                    }
                except Exception as child_exc:
                    errors.append(f"child navigation failed: {child_exc}")

            if child_data:
                extras["child"] = child_data

            return {
                "run_id": run_id,
                "results": results,
                "observation": observation,
                "console": console_lines,
                "links": link_probes,
                "dom_scan": dom_scan,
                "extras": extras,
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
                "extras": {},
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
    follow_one_link: bool = True,
) -> Dict[str, Any]:
    """Run the Playwright executor with optional slow motion."""

    if not target_url:
        raise ValueError("target_url is required")

    return asyncio.run(
        _run_audit_async(
            target_url=target_url,
            run_id=run_id,
            slow_ms=slow_ms,
            follow_one_link=follow_one_link,
        )
    )
