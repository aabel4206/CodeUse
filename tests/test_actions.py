import asyncio
import os
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from tool.executor import actions


@pytest.mark.asyncio
async def test_hover_and_styles(test_page_url: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto(test_page_url)

        selector = "[data-testid='btn-campaign']"
        result = await actions.hover(page, selector)
        assert result["ok"] is True

        base_style = await actions.get_computed_style(page, selector, "")
        hover_style = await actions.get_computed_style(page, selector, ":hover")

        for style in (base_style, hover_style):
            assert "transform" in style
            assert "transitionDuration" in style
            assert "transitionTimingFunction" in style

        await browser.close()


@pytest.mark.asyncio
async def test_measure_hover_metrics(test_page_url: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto(test_page_url)

        selector = "[data-testid='btn-campaign']"
        metrics = await actions.measure_hover_metrics(page, selector)
        assert "before" in metrics and "after" in metrics
        assert "transitionDuration_ms" in metrics["before"]
        assert "transitionDuration_ms" in metrics["after"]

        await browser.close()


@pytest.mark.asyncio
async def test_dom_helpers_and_url(test_page_url: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto(test_page_url)

        selector = "[data-testid='btn-campaign']"
        bbox = await actions.get_bounding_client_rect(page, selector)
        assert {"x", "y", "width", "height"} <= set(bbox)

        text = await actions.get_text(page, selector)
        assert "Load Metrics" in text

        current = await actions.current_url(page)
        assert current.startswith("http://127.0.0.1")

        await browser.close()


@pytest.mark.asyncio
async def test_screenshot_creates_file(test_page_url: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto(test_page_url)

        run_id = "test-run-actions"
        label = "capture"
        path = await actions.screenshot(page, run_id, label)
        assert Path(path).exists()

        # Clean up to avoid polluting the repo.
        Path(path).unlink(missing_ok=True)
        (Path(path).parent).rmdir()

        await browser.close()
