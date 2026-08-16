"""Phase 8: Frontend validation with Playwright.

Asserts that typing into the Sphinx search box and hitting Enter fires a
request to /api/search and renders custom OpenSearch results into the DOM.

Run with:
    playwright install chromium   # first time only
    pytest tests/test_frontend.py -v

Prerequisites: FastAPI app running on :8000, docs built + indexed.
"""
from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("POC_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def browser_context(browser):
    context = browser.new_context()
    yield context
    context.close()


def test_search_form_hits_opensearch_endpoint(browser_context):
    page: Page = browser_context.new_page()

    # Capture all requests so we can assert one hit /api/search.
    api_requests: list[str] = []
    page.on("request", lambda req: api_requests.append(req.url))

    page.goto(BASE_URL)

    # The canonical-sphinx sidebar search form.
    form = page.locator("form.sidebar-search-container")
    form.wait_for(timeout=15000)

    # Type "broker" and submit (Enter triggers the form's submit handler).
    input_box = form.locator("input.sidebar-search")
    input_box.fill("broker")
    input_box.press("Enter")

    # Assert the network request to /api/search?q=broker was made.
    page.wait_for_timeout(2000)  # allow fetch + render
    assert any(
        re.search(r"/api/search\?q=broker", url) for url in api_requests
    ), f"No /api/search request captured. Saw: {api_requests}"

    # Assert the DOM updated with custom OpenSearch results.
    result = page.locator(".opensearch-result-item").first
    expect(result).to_be_visible(timeout=10000)

    # And that at least one result links to a real doc URL.
    link = result.locator("a")
    href = link.get_attribute("href")
    assert href and href.startswith("/"), f"Unexpected href: {href}"

    page.close()
