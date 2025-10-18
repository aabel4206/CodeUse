"""Core Playwright actions used by the executor service."""

from pathlib import Path
from typing import Dict, Any

from playwright.async_api import Page

SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


async def hover(page: Page, selector: str) -> Dict[str, Any]:
    """Hover over the element matching ``selector``."""
    await page.wait_for_selector(selector)
    await page.hover(selector)
    await page.wait_for_timeout(200)
    return {"ok": True}


async def get_computed_style(
    page: Page, selector: str, pseudo: str = ":hover"
) -> Dict[str, Any]:
    """Return selected computed style values for an element (optionally a pseudo state)."""

    js = """
        (sel, pseudo) => {
            const el = document.querySelector(sel);
            if (!el) {
                throw new Error(`Element not found for selector: ${sel}`);
            }
            const computed = getComputedStyle(el, pseudo);
            return {
                transform: computed.transform,
                transitionDuration: computed.transitionDuration,
                transitionTimingFunction: computed.transitionTimingFunction
            };
        }
    """

    return await page.evaluate(js, selector, pseudo)


async def screenshot(page: Page, label: str) -> str:
    """Capture a screenshot and return a relative path to the file."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{label}.png"
    await page.screenshot(path=str(path))
    return str(path)
