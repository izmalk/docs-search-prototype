# Bill of Materials

Everything required to run the OpenSearch-backed Sphinx search PoC locally.

## Host dependencies (Ubuntu 24.04 LTS recommended)

| Component | Version | Install |
|-----------|---------|---------|
| LXD | 6.1+ | `sudo snap install lxd` |
| Juju | 3.5+ (3/stable) | `sudo snap install juju --channel 3/stable` |
| Terraform | 1.6+ | [hashicorp.com](https://developer.hashicorp.com/terraform/install) |
| Python | 3.10+ | system |
| jq | any | `sudo snap install jq` |
| Node.js | 18+ (Playwright only) | [nodejs.org](https://nodejs.org/) |

### Host kernel parameters (set by `bootstrap-env.sh`)

```
vm.max_map_count      = 262144
vm.swappiness         = 0
net.ipv4.tcp_retries2 = 5
fs.file-max           = 1048576
```

## Juju charms (deployed via Terraform)

| Charm | Channel | Units | Purpose |
|-------|---------|-------|---------|
| `opensearch` (machine) | `2/stable` | 1 | OpenSearch backend (`profile=testing`, 1 GB heap) |
| `self-signed-certificates` | `latest/stable` | 1 | TLS — OpenSearch refuses to start without it |
| `data-integrator` | `latest/stable` | 1 | Creates the `sphinx-docs` index + admin credentials |

### Integrations

- `opensearch:certificates` ↔ `self-signed-certificates:certificates` (provided by the upstream Terraform module)
- `opensearch:opensearch-client` ↔ `data-integrator:opensearch-client` (hand-written in `terraform/main.tf`)

## Python libraries (see `requirements.txt`)

| Library | Purpose |
|---------|---------|
| `opensearch-py` | OpenSearch client (indexer + app) |
| `beautifulsoup4` | HTML stripping from `.fjson` body fields |
| `fastapi` | Middleware proxy |
| `uvicorn[standard]` | ASGI server |
| `python-dotenv` | Load `.env` credentials |
| `requests` | Backend integration tests |
| `pytest` | Test runner |
| `playwright` | Frontend validation |

## Data source

| Repo | Path used | Build outputs |
|------|-----------|---------------|
| `canonical/kafka-operator` | `docs/` | `_build/json` (`.fjson`), `_build/dirhtml` (UI) |

The Kafka docs use the Canonical Sphinx Stack (`canonical_sphinx` theme, MyST
Markdown). Their own `docs/requirements.txt` is installed into a dedicated
venv at `vendor/kafka-operator/docs/.venv` by `scripts/build-docs.sh`.
