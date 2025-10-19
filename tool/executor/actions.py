"""Core Playwright actions used by the executor service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Union

from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

RUNS_ROOT = Path(__file__).resolve().parent / "runs"


def _run_dir(run_id: str) -> Path:
    """Return the artifact directory for a run, creating it if needed."""
    run_path = RUNS_ROOT / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


async def _ensure_visible(page: Page, selector: str, timeout_ms: int = 5000) -> None:
    """Wait for ``selector`` to be visible, raising a helpful error on timeout."""
    if not selector:
        raise ValueError("Selector is required.")
    try:
        await page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            f"Timed out waiting for selector '{selector}' to become visible."
        ) from exc


async def hover(page: Page, selector: str, *, slow_ms: int = 0) -> Dict[str, Any]:
    """Hover over the element matching ``selector`` with optional slow motion."""
    await page.wait_for_selector(selector, state="visible")
    await page.hover(selector)
    wait_ms = 200 + max(slow_ms, 0)
    await page.wait_for_timeout(wait_ms)
    return {"ok": True}


async def click(page: Page, selector: str, *, slow_ms: int = 0) -> Dict[str, Any]:
    """Click the element matching ``selector`` with optional slow motion."""
    await page.wait_for_selector(selector, state="visible")
    await page.click(selector)
    wait_ms = 100 + max(slow_ms, 0)
    await page.wait_for_timeout(wait_ms)
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


async def measure_hover_metrics(page: Page, selector: str, *, slow_ms: int = 0) -> Dict[str, Any]:
    """Capture before/after computed styles for hover transitions."""
    before = await get_computed_style(page, selector, "")
    await hover(page, selector, slow_ms=slow_ms)
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


async def navigate(page: Page, url: str, timeout_ms: int = 10_000) -> Dict[str, Any]:
    """Navigate to ``url`` and report the resulting page URL."""
    if not url:
        raise ValueError("URL is required.")
    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be a positive integer.")
    try:
        await page.goto(url, timeout=timeout_ms)
    except PlaywrightTimeoutError as exc:
        raise ValueError(f"Timed out navigating to '{url}'.") from exc
    return {"ok": True, "url": page.url}


async def scan_links(page: Page) -> Dict[str, Any]:
    """Collect all anchor elements with hrefs and probe their status codes."""
    link_data = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
            href: a.getAttribute('href'),
            url: a.href,
            text: (a.innerText || '').trim()
        }))
        """
    )

    probes: List[Dict[str, Any]] = []
    for item in link_data:
        url = item.get("url")
        status = 0
        try:
            if url:
                response = await page.request.get(url)
                status = response.status
        except Exception:
            status = 0
        probes.append(
            {
                "href": item.get("href"),
                "url": url,
                "status": status,
                "text": item.get("text"),
            }
        )
    return {"links": probes}


async def scan_images(page: Page) -> Dict[str, Any]:
    """Scan images for accessibility issues such as missing alt text and unnamed clickables."""
    return await page.evaluate(
        r"""
        () => {
            const summarize = (el) => {
                if (!el) return 'unknown';
                const id = el.id ? `#${el.id}` : '';
                const classes = (typeof el.className === 'string' && el.className.length > 0)
                    ? '.' + el.className.trim().split(/\s+/).filter(Boolean).join('.')
                    : '';
                const tag = el.tagName ? el.tagName.toLowerCase() : 'node';
                const label = (tag + id + classes).trim();
                return label || tag;
            };

            const images = Array.from(document.querySelectorAll('img'));
            const missingAlt = images.filter(
                img => !(img.getAttribute('alt') || '').trim()
            ).map(img => ({
                src: img.getAttribute('src'),
                selector: summarize(img)
            }));

            const clickableSelectors = Array.from(document.querySelectorAll(
                'button, a, [role=\"button\"], [tabindex]'
            ));
            const withoutName = clickableSelectors.filter(el => {
                const hasText = (el.innerText || '').trim().length > 0;
                const hasAria = (el.getAttribute('aria-label') || '').trim().length > 0;
                return !(hasText || hasAria);
            }).map(summarize);

            return {
                img_missing_alt_count: missingAlt.length,
                missing_alt_examples: missingAlt.slice(0, 4),
                clickables_without_name: withoutName,
            };
        }
        """
    )


async def measure_target(page: Page, selector: str) -> Dict[str, Any]:
    """Measure width/height of a target element."""
    bbox = await get_bounding_client_rect(page, selector)
    return {"selector": selector, "bbox": bbox}


async def detect_overlap(page: Page, selector: str) -> Dict[str, Any]:
    """Detect elements overlapping the center point of ``selector``."""
    overlaps = await page.evaluate(
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
                const classes = (typeof topEl.className === 'string' && topEl.className.length > 0)
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
    return {"selector": selector, "overlaps": overlaps}


async def dblclick(page: Page, selector: str) -> Dict[str, Any]:
    """Double-click the element matching ``selector``."""
    await _ensure_visible(page, selector)
    await page.dblclick(selector)
    return {"ok": True}


async def type_text(
    page: Page, selector: str, text: str, delay_ms: int = 0
) -> Dict[str, Any]:
    """Type ``text`` into the element matching ``selector``."""
    if text is None:
        raise ValueError("text must not be None.")
    if delay_ms < 0:
        raise ValueError("delay_ms cannot be negative.")
    await _ensure_visible(page, selector)
    await page.click(selector)
    await page.type(selector, text, delay=delay_ms)
    return {"ok": True}


async def press(page: Page, selector: str, key: str) -> Dict[str, Any]:
    """Press ``key`` while the element matching ``selector`` is focused."""
    if not key:
        raise ValueError("key is required.")
    await _ensure_visible(page, selector)
    await page.press(selector, key)
    return {"ok": True}


async def fill(page: Page, selector: str, value: str) -> Dict[str, Any]:
    """Fill the element matching ``selector`` with ``value``."""
    if value is None:
        raise ValueError("value must not be None.")
    await _ensure_visible(page, selector)
    await page.fill(selector, value)
    return {"ok": True}


async def check(page: Page, selector: str) -> Dict[str, Any]:
    """Check a checkbox or radio button."""
    await _ensure_visible(page, selector)
    await page.check(selector)
    return {"ok": True}


async def uncheck(page: Page, selector: str) -> Dict[str, Any]:
    """Uncheck a checkbox."""
    await _ensure_visible(page, selector)
    await page.uncheck(selector)
    return {"ok": True}


async def select_option(
    page: Page, selector: str, value: Union[str, Sequence[str]]
) -> Dict[str, Any]:
    """Select one or more option values."""
    await _ensure_visible(page, selector)
    if isinstance(value, str):
        values = [value]
    else:
        values = list(value)
    if not values:
        raise ValueError("At least one option value must be provided.")
    selected = await page.select_option(
        selector, values if len(values) > 1 else values[0]
    )
    return {"ok": True, "selected": [item for item in selected if item is not None]}


async def assert_text(page: Page, selector: str, contains: str) -> Dict[str, Any]:
    """Assert that the element text includes ``contains``."""
    if not contains:
        raise ValueError("contains is required.")
    await page.wait_for_selector(selector, state="visible")
    text = await page.text_content(selector) or ""
    if contains not in text:
        raise ValueError(f"Expected '{contains}' in text for selector '{selector}'. Found: '{text}'.")
    return {"ok": True, "text": text}


async def check_link(page: Page, selector: str, label: Optional[str] = None) -> Dict[str, Any]:
    """Fetch the status code for the link matching ``selector``."""
    info = await page.evaluate(
        """
        (sel) => {
            const el = document.querySelector(sel);
            if (!el) throw new Error(`Element not found for selector: ${sel}`);
            return {
                href: el.getAttribute('href'),
                url: el.href,
                text: (el.innerText || '').trim()
            };
        }
        """,
        selector,
    )
    status = 0
    try:
        if info.get("url"):
            response = await page.request.get(info["url"])
            status = response.status
    except Exception:
        status = 0
    info.update({"status": status, "label": label})
    return info


async def check_disabled(page: Page, selector: str) -> Dict[str, Any]:
    """Return whether the element appears disabled."""
    disabled = await page.evaluate(
        """
        (sel) => {
            const el = document.querySelector(sel);
            if (!el) throw new Error(`Element not found for selector: ${sel}`);
            const aria = el.getAttribute('aria-disabled');
            if (aria && aria.toLowerCase() === 'true') return true;
            if (el.disabled !== undefined) return Boolean(el.disabled);
            return el.hasAttribute('disabled');
        }
        """,
        selector,
    )
    return {"selector": selector, "disabled": bool(disabled)}


async def count_elements(page: Page, selector: str) -> Dict[str, Any]:
    """Count elements matching ``selector``."""
    count = await page.evaluate(
        "(sel) => document.querySelectorAll(sel).length",
        selector,
    )
    return {"selector": selector, "count": int(count)}


async def drag_and_drop(page: Page, source: str, target: str) -> Dict[str, Any]:
    """Drag from ``source`` selector to ``target`` selector."""
    await _ensure_visible(page, source)
    await _ensure_visible(page, target)
    await page.drag_and_drop(source, target)
    return {"ok": True}


async def scroll_to(page: Page, x: int = 0, y: int = 0) -> Dict[str, Any]:
    """Scroll the window to ``(x, y)``."""
    await page.evaluate(
        "({x, y}) => window.scrollTo(x, y)", {"x": int(x), "y": int(y)}
    )
    return {"ok": True}


async def wait_for_selector(
    page: Page,
    selector: str,
    state: Literal["attached", "detached", "visible", "hidden"] = "visible",
    timeout_ms: int = 5000,
) -> Dict[str, Any]:
    """Wait for ``selector`` to reach ``state``."""
    if state not in {"attached", "detached", "visible", "hidden"}:
        raise ValueError(
            "state must be one of 'attached', 'detached', 'visible', or 'hidden'."
        )
    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be a positive integer.")
    try:
        await page.wait_for_selector(selector, state=state, timeout=timeout_ms)
    except PlaywrightTimeoutError as exc:
        raise ValueError(
            f"Timed out waiting for selector '{selector}' to become {state}."
        ) from exc
    return {"ok": True, "state": state}


async def get_attribute(page: Page, selector: str, name: str) -> Dict[str, Any]:
    """Return the attribute ``name`` value for ``selector``."""
    if not name:
        raise ValueError("name is required.")
    await _ensure_visible(page, selector)
    value = await page.get_attribute(selector, name)
    return {"ok": True, "name": name, "value": value}


async def screenshot_fullpage(page: Page, run_id: str, label: str) -> Dict[str, Any]:
    """Capture a full-page screenshot and return its path."""
    run_dir = _run_dir(run_id)
    path = run_dir / f"{label}.png"
    await page.screenshot(path=str(path), full_page=True)
    return {"ok": True, "path": str(path)}


async def start_tracing(
    context: BrowserContext, screenshots: bool = True, snapshots: bool = True
) -> Dict[str, Any]:
    """Start Playwright tracing for the provided browser context."""
    if context is None:
        raise ValueError("context is required.")
    await context.tracing.start(screenshots=screenshots, snapshots=snapshots)
    return {"ok": True}


async def stop_tracing(
    context: BrowserContext, run_id: str, label: str = "trace"
) -> Dict[str, Any]:
    """Stop tracing and persist the trace archive."""
    if context is None:
        raise ValueError("context is required.")
    run_dir = _run_dir(run_id)
    path = run_dir / f"{label}.zip"
    await context.tracing.stop(path=str(path))
    return {"ok": True, "path": str(path)}


# if __name__ == "__main__":
#     import asyncio
#     from playwright.async_api import async_playwright
#
#     async def _demo():
#         async with async_playwright() as pw:
#             browser = await pw.chromium.launch(headless=False, slow_mo=250)
#             context = await browser.new_context()
#             page = await context.new_page()
#             await navigate(page, "http://localhost:5173")
#             await wait_for_selector(page, "#btn1")
#             await click(page, "#btn1")
#             await type_text(page, "#name", "Playwright")
#             await screenshot_fullpage(page, "demo123", "after")
#             await context.close()
#             await browser.close()
#
#     asyncio.run(_demo())
