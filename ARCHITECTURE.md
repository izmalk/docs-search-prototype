# Architecture

```mermaid
flowchart TB
    subgraph Host["LXD host (Ubuntu)"]
        Sysctl["Host sysctl<br/>vm.max_map_count=262144<br/>vm.swappiness=0<br/>net.ipv4.tcp_retries2=5"]
    end

    subgraph IaaC["IaaC layer (Terraform + Juju)"]
        TF["terraform/main.tf"]
        Model["juju_model: sphinx-search<br/>cloudinit-userdata → sysctl in containers"]
        OS["opensearch charm<br/>profile=testing, 1 unit"]
        TLS["self-signed-certificates charm"]
        DI["data-integrator charm<br/>index-name=sphinx-docs"]
        TF --> Model
        Model --> OS
        Model --> TLS
        Model --> DI
        OS ---|certificates| TLS
        OS ---|opensearch-client| DI
    end

    subgraph Ingest["Data ingestion flow"]
        Clone["Clone kafka-operator"]
        BuildJSON["sphinx-build -b json<br/>→ .fjson files"]
        BuildHTML["sphinx-build -b dirhtml<br/>→ UI files"]
        Indexer["indexer.py"]
        OSIndex[("OpenSearch<br/>sphinx-docs index")]
        Clone --> BuildJSON --> Indexer
        Clone --> BuildHTML
        Indexer -->|bulk insert| OSIndex
    end

    subgraph Web["User web flow"]
        Browser["Browser<br/>Sphinx dirhtml UI"]
        FastAPI["FastAPI app.py<br/>:8000"]
        API["/api/search?q=..."]
        Browser -->|search form submit| API
        API --> FastAPI
        FastAPI -->|multi_match query| OSIndex
        FastAPI -->|JSON results| Browser
        FastAPI -->|serve static files| BuildHTML
    end

    Sysctl -.->|required by| OS
    DI -.->|get-credentials action| Creds[".env<br/>host/user/password"]
    Creds -.->|load_dotenv| Indexer
    Creds -.->|load_dotenv| FastAPI
```

## Flow summary

1. **IaaC** — `bootstrap-env.sh` tunes the host and bootstraps LXD + Juju; `terraform apply` deploys OpenSearch, self-signed-certificates, and data-integrator, then `fetch-credentials.sh` extracts credentials to `.env`.
2. **Ingestion** — `build-docs.sh` clones the Kafka Operator docs, builds them in JSON and dirhtml formats, and `indexer.py` bulk-loads the `.fjson` content into the `sphinx-docs` OpenSearch index.
3. **Web** — `app.py` (FastAPI) serves the dirhtml build at `/` and exposes `/api/search`, which queries OpenSearch with a `multi_match` on `title^3, body`. The injected `custom_search.js` intercepts the sidebar search form and renders results as `.opensearch-result-item` nodes.

## Security boundary

OpenSearch credentials live only in `.env` on the host and are loaded by
`indexer.py` and `app.py`. They never appear in the browser — the FastAPI
proxy is the sole client of OpenSearch, which is the core design goal of the
PoC.
