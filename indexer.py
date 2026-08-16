#!/usr/bin/env python3
"""Phase 4: Ingest Sphinx JSON (.fjson) build output into OpenSearch.

Reads the `.fjson` files produced by `sphinx-build -b json`, sanitises the
content (strip HTML from `body`, derive a clean URL slug matching the dirhtml
output), and bulk-inserts the documents into the local OpenSearch cluster.

Idempotent: drops and recreates the index on every run so repeated test cycles
always start from a clean slate.

Usage:
    python indexer.py [--json-dir vendor/kafka-operator/docs/_build/json]
                      [--index sphinx-docs]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterator

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from opensearchpy import OpenSearch, helpers

# Pages that are Sphinx infrastructure, not real documentation content.
SKIP_STEMS = {"genindex", "search", "404", "index"}


def get_client() -> OpenSearch:
    """Build an OpenSearch client from .env credentials.

    TLS verification is disabled because the cluster uses self-signed
    certificates from the self-signed-certificates charm.
    """
    load_dotenv()
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


INDEX_MAPPING = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "title": {"type": "text", "analyzer": "standard"},
            "body": {"type": "text", "analyzer": "standard"},
            "url": {"type": "keyword"},
            "anchor": {"type": "keyword"},
        }
    },
}


def strip_html(html: str) -> str:
    """Collapse HTML to plain text, preserving readable whitespace."""
    soup = BeautifulSoup(html or "", "html.parser")
    # Drop script/style blocks that would otherwise leak into the index.
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return " ".join(text.split()).strip()


def fjson_to_url(rel_path: Path) -> str:
    """Map a .fjson path to the URL slug served by the dirhtml build.

    `how-to/clients.fjson` -> `/how-to/clients/`
    `index.fjson`          -> `/`
    """
    stem = rel_path.with_suffix("").as_posix()  # drop .fjson
    if stem == "index":
        return "/"
    return f"/{stem}/"


def iter_documents(json_dir: Path, index: str) -> Iterator[dict]:
    """Yield OpenSearch bulk-action dicts for every content .fjson file."""
    for fjson in sorted(json_dir.rglob("*.fjson")):
        rel = fjson.relative_to(json_dir)
        stem = rel.with_suffix("").as_posix()
        # Skip Sphinx infrastructure pages and per-section index pages named
        # `index` that live in subdirectories (they duplicate the parent TOC).
        if Path(stem).name in SKIP_STEMS and stem != "index":
            continue

        try:
            doc = json.loads(fjson.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ! skipping {rel}: {exc}", file=sys.stderr)
            continue

        title = doc.get("title", "").strip()
        body = strip_html(doc.get("body", ""))
        if not title and not body:
            continue

        url = fjson_to_url(rel)
        source = {
            "title": title,
            "body": body,
            "url": url,
            "anchor": "",
        }
        yield {
            "_index": index,
            "_id": url,  # idempotent: same URL overwrites
            "_source": source,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-dir",
        default=os.environ.get(
            "SPHINX_JSON_DIR", "vendor/kafka-operator/docs/_build/json"
        ),
        help="Directory containing the Sphinx JSON build output (.fjson files).",
    )
    parser.add_argument(
        "--index",
        default=os.environ.get("OPENSEARCH_INDEX", "sphinx-docs"),
        help="OpenSearch index name.",
    )
    args = parser.parse_args()

    json_dir = Path(args.json_dir)
    if not json_dir.is_dir():
        print(f"JSON build dir not found: {json_dir}", file=sys.stderr)
        print("Run scripts/build-docs.sh first.", file=sys.stderr)
        return 2

    client = get_client()

    # Idempotent: drop + recreate the index.
    if client.indices.exists(index=args.index):
        print(f"Deleting existing index '{args.index}'...")
        client.indices.delete(index=args.index)

    print(f"Creating index '{args.index}'...")
    client.indices.create(index=args.index, body=INDEX_MAPPING)

    print(f"Indexing .fjson files from {json_dir}...")
    success, errors = helpers.bulk(
        client, iter_documents(json_dir, args.index), raise_on_error=False
    )
    if errors:
        print(f"  {len(errors)} documents failed to index.", file=sys.stderr)
        for e in errors[:5]:
            print(f"    {e}", file=sys.stderr)

    client.indices.refresh(index=args.index)
    count = client.count(index=args.index)["count"]
    print(f"Done. Indexed {success} documents; index now holds {count} docs.")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
