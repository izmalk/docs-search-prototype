"""Phase 5: FastAPI middleware that serves the Sphinx dirhtml build and
exposes an `/api/search` endpoint backed by OpenSearch.

The OpenSearch credentials live only here (loaded from .env) — they never
reach the browser, which is the whole point of the proxy.

Run:
    uvicorn app:app --reload --port 8000
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from opensearchpy import OpenSearch

load_dotenv()

DOCS_DIR = Path(
    os.environ.get("SPHINX_HTML_DIR", "vendor/kafka-operator/docs/_build/dirhtml")
)
INDEX = os.environ.get("OPENSEARCH_INDEX", "sphinx-docs")

app = FastAPI(title="Sphinx-OpenSearch PoC")


def get_client() -> OpenSearch:
    host = os.environ["OPENSEARCH_HOST"]
    port = int(os.environ.get("OPENSEARCH_PORT", "9200"))
    user = os.environ["OPENSEARCH_USER"]
    password = os.environ["OPENSEARCH_PASSWORD"]
    verify = os.environ.get("OPENSEARCH_VERIFY_CERTS", "false").lower() == "true"
    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=(user, password),
        use_ssl=True,
        verify_certs=verify,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )


# A single client is fine for a local PoC; created lazily so importing the
# module (e.g. by tests) doesn't require OpenSearch to be reachable.
_client: OpenSearch | None = None


def client() -> OpenSearch:
    global _client
    if _client is None:
        _client = get_client()
    return _client


@app.get("/api/search")
def search(q: str = Query(..., min_length=1, description="Search query")):
    """Query OpenSearch and return a clean JSON array of results.

    Uses a `multi_match` query boosting `title` over `body` so that pages
    whose title matches rank higher.
    """
    body = {
        "size": 20,
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["title^3", "body"],
                "type": "best_fields",
                "operator": "and",
            }
        },
        # Fall back to `or` if `and` returns nothing — friendlier UX.
        "fallback": {
            "query": {
                "multi_match": {
                    "query": q,
                    "fields": ["title^3", "body"],
                    "type": "best_fields",
                }
            }
        },
    }

    resp = client().search(index=INDEX, body={"query": body["query"], "size": 20})

    hits = resp.get("hits", {}).get("hits", [])
    if not hits:
        # Try the fallback (any-term) query.
        resp = client().search(index=INDEX, body={"query": body["fallback"]["query"], "size": 20})
        hits = resp.get("hits", {}).get("hits", [])

    results = []
    for hit in hits:
        src = hit["_source"]
        snippet = src.get("body", "")
        if len(snippet) > 200:
            snippet = snippet[:200].rsplit(" ", 1)[0] + "…"
        results.append(
            {
                "title": src.get("title", ""),
                "url": src.get("url", ""),
                "snippet": snippet,
                "score": hit.get("_score", 0),
            }
        )
    return JSONResponse(results)


# Mount the compiled Sphinx dirhtml output at the root. This MUST come after
# the /api route above, otherwise the catch-all static handler would shadow it.
if DOCS_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(DOCS_DIR), html=True), name="docs")
else:
    @app.get("/")
    def docs_not_built():
        return JSONResponse(
            {"error": f"Docs build not found at {DOCS_DIR}. Run scripts/build-docs.sh first."},
            status_code=503,
        )
