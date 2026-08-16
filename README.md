# docs-search-prototype

Proof-of-Concept replacing Sphinx's default client-side search (`searchindex.js`)
with a server-side **OpenSearch** backend, deployed on a local LXD/Juju cloud
via Terraform, with a FastAPI proxy that keeps database credentials off the
browser.

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the Mermaid diagram and flow
summary. Bill of materials: [`BOM.md`](BOM.md).

## Deployment

For a full step-by-step guide to deploying in a Multipass VM and accessing
the Docs UI from the host laptop, see [`DEPLOYMENT.md`](DEPLOYMENT.md).

## Quick start

```bash
# 1. Bootstrap host: LXD, Juju controller, OpenSearch sysctl.
./bootstrap-env.sh

# 2. Deploy OpenSearch + data-integrator via Terraform.
cd terraform
terraform init
terraform apply
cd ..

# 3. Fetch OpenSearch credentials into .env.
./scripts/fetch-credentials.sh

# 4. Build the Kafka Operator docs (JSON + dirhtml) and inject custom_search.js.
./scripts/build-docs.sh

# 5. Index the .fjson output into OpenSearch.
python indexer.py

# 6. Serve the docs + /api/search.
uvicorn app:app --port 8000

# 7. Validate (in another terminal).
pytest tests/ -v
```

## What proves it works

- `tests/test_poc.py` renames `searchindex.js` (breaking Sphinx's native search)
  and asserts `/api/search?q=zookeeper` still returns real Kafka doc titles.
- `tests/test_frontend.py` (Playwright) types "broker" into the sidebar search
  box, captures the `/api/search?q=broker` network request, and asserts
  `.opensearch-result-item` nodes appear in the DOM.

## Layout

```
bootstrap-env.sh          Host + LXD + Juju bootstrap, sysctl tuning
terraform/                Juju provider manifests (reuses upstream opensearch module)
scripts/
  fetch-credentials.sh    data-integrator get-credentials → .env
  build-docs.sh           Clone kafka-operator, build JSON + dirhtml
indexer.py                .fjson → OpenSearch bulk insert
app.py                    FastAPI: serve dirhtml + /api/search
static/custom_search.js   Injected into Sphinx; intercepts the search form
tests/                    Backend + negation + Playwright suites
BOM.md  ARCHITECTURE.md   Handover deliverables
```