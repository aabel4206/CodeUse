"""Core Playwright actions used by the executor service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from playwright.async_api import Page

RUNS_ROOT = Path(__file__).resolve().parent / "runs"


def _run_dir(run_id: str) -> Path:
    """Return the artifact directory for a run, creating it if needed."""
    run_path = RUNS_ROOT / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


async def hover(page: Page, selector: str) -> Dict[str, Any]:
    """Hover over the element matching ``selector``."""
    await page.wait_for_selector(selector, state="visible")
    await page.hover(selector)
    await page.wait_for_timeout(200)  # allow animations to complete
    return {"ok": True}


async def click(page: Page, selector: str) -> Dict[str, Any]:
    """Click the element matching ``selector``."""
    await page.wait_for_selector(selector, state="visible")
    await page.click(selector)
    await page.wait_for_timeout(100)  # brief pause for DOM updates
    return {"ok": True}


async def get_computed_style(page: Page, selector: str, pseudo: str = "") -> Dict[str, Any]:
    """Return selected computed style values for an element (optionally in a pseudo state)."""

    js = """
        ({ sel, pseudo }) => {
            const el = document.querySelector(sel);
            if (!el) {
                throw new Error(`Element not found for selector: ${sel}`);
            }
            const targetPseudo = pseudo && pseudo.length ? pseudo : null;
            const computed = getComputedStyle(el, targetPseudo);
            return {
                transform: computed.transform,
                transitionDuration: computed.transitionDuration,
                transitionTimingFunction: computed.transitionTimingFunction
            };
        }
    """

    return await page.evaluate(js, {"sel": selector, "pseudo": pseudo})


def _parse_duration_to_ms(duration: str) -> Optional[float]:
    """Convert CSS duration strings (e.g., '0.2s', '150ms') to milliseconds; return None on failure."""
    try:
        value = duration.strip().lower()
        if value.endswith("ms"):
            return float(value[:-2])
        if value.endswith("s"):
            return float(value[:-1]) * 1000.0
    except (ValueError, AttributeError):
        return None
    return None


async def measure_hover_metrics(page: Page, selector: str) -> Dict[str, Any]:
    """Capture before/after computed styles for hover transitions."""
    before = await get_computed_style(page, selector, "")
    await hover(page, selector)
    after = await get_computed_style(page, selector, ":hover")

    return {
        "before": {
            "transform": before["transform"],
            "transitionDuration_ms": _parse_duration_to_ms(before["transitionDuration"]),
            "transitionTimingFunction": before["transitionTimingFunction"],
        },
        "after": {
            "transform": after["transform"],
            "transitionDuration_ms": _parse_duration_to_ms(after["transitionDuration"]),
            "transitionTimingFunction": after["transitionTimingFunction"],
        },
    }


async def get_bounding_client_rect(page: Page, selector: str) -> Dict[str, Any]:
    """Return the bounding client rect for the first element that matches ``selector``."""
    js = """
        ({ sel }) => {
            const el = document.querySelector(sel);
            if (!el) {
                throw new Error(`Element not found for selector: ${sel}`);
            }
            const rect = el.getBoundingClientRect();
            return {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height
            };
        }
    """
    return await page.evaluate(js, {"sel": selector})


async def get_text(page: Page, selector: str) -> str:
    """Return the text content for the element matching ``selector``."""
    await page.wait_for_selector(selector, state="attached")
    content = await page.text_content(selector)
    return content or ""


async def current_url(page: Page) -> str:
    """Return the current page URL."""
    return page.url


async def screenshot(page: Page, run_id: str, label: str) -> str:
    """Capture a screenshot for the provided run and return the file path."""
    run_dir = _run_dir(run_id)
    path = run_dir / f"{label}.png"
    await page.screenshot(path=str(path))
    return str(path)
