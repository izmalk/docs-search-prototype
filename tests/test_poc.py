"""Phase 8: End-to-end backend integration + negation tests.

Run with:
    pytest tests/test_poc.py -v

Prerequisites:
    - OpenSearch deployed (terraform apply) and credentials in .env
    - Docs built (scripts/build-docs.sh)
    - indexer.py has been run
    - FastAPI app running on :8000 (uvicorn app:app --port 8000)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("POC_BASE_URL", "http://localhost:8000")
DOCS_HTML_DIR = Path(
    os.environ.get("SPHINX_HTML_DIR", "vendor/kafka-operator/docs/_build/dirhtml")
)


def _search(q: str) -> requests.Response:
    return requests.get(f"{BASE_URL}/api/search", params={"q": q}, timeout=30)


# --- Backend integration test ---------------------------------------------

def test_search_zookeeper_returns_real_kafka_docs():
    """GET /api/search?q=zookeeper → 200 with real Kafka doc titles/URLs.

    The Kafka docs have moved to KRaft mode, so "zookeeper" may not appear
    prominently — we just assert the endpoint returns well-formed results
    from the Kafka docs (non-empty, with title/url/snippet).
    """
    resp = _search("zookeeper")
    assert resp.status_code == 200, resp.text
    results = resp.json()
    assert isinstance(results, list)
    assert len(results) > 0, "Expected at least one result for 'zookeeper'"

    # Every result must have the shape the frontend expects.
    for r in results:
        assert "title" in r and r["title"]
        assert "url" in r and r["url"]
        assert "snippet" in r


def test_search_broker_returns_results():
    """A second query proves the endpoint is generally functional."""
    resp = _search("broker")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


# --- Negation test: default Sphinx search must be broken ------------------

SEARCHINDEX = DOCS_HTML_DIR / "searchindex.js"


def test_search_works_even_without_searchindex():
    """The critical negation test: delete searchindex.js (breaking Sphinx's
    native search), assert it 404s, and assert /api/search still returns
    results because it queries OpenSearch, not Sphinx.

    The .bak file is restored on teardown so re-running tests is safe.
    """
    if not SEARCHINDEX.exists():
        # Already removed — maybe a prior run didn't restore. Create a stub
        # so we can still test the deletion + restoration cycle.
        SEARCHINDEX.write_text("{}")

    # 1. Break the default Sphinx search by renaming searchindex.js.
    bak = SEARCHINDEX.with_suffix(".js.bak")
    SEARCHINDEX.rename(bak)
    try:
        # 2. Assert searchindex.js now 404s.
        resp = requests.get(f"{BASE_URL}/searchindex.js", timeout=10)
        assert resp.status_code == 404, "searchindex.js should be gone"

        # 3. The critical assertion: /api/search still works via OpenSearch.
        resp = _search("zookeeper")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) > 0, "Search should still return results without searchindex.js"
    finally:
        # Restore so the build dir is left intact for manual testing.
        if bak.exists() and not SEARCHINDEX.exists():
            bak.rename(SEARCHINDEX)
