# Deployment Guide — Multipass VM

Step-by-step instructions to deploy the OpenSearch-backed Sphinx search PoC
inside a Multipass VM and access the Docs UI from the hosting laptop.

## Prerequisites (host laptop)

| Tool | Version | Install |
|------|---------|---------|
| Multipass | 1.16+ | `sudo snap install multipass` |
| `curl` + `jq` | any | `sudo apt install curl jq` |

No other tools are required on the host — everything else runs inside the VM.

---

## Step 1 — Create (or reuse) a Multipass VM

Create a VM with at least 4 CPUs, 16 GB RAM, and 50 GB disk (OpenSearch is
resource-hungry):

```bash
multipass launch --name opensearch-test --cpus 8 --memory 16G --disk 100G 24.04
```

If you already have a suitable VM, start it:

```bash
multipass start opensearch-test
```

Note the VM's IP address — you'll need it to access the UI from the host:

```bash
VM_IP=$(multipass info opensearch-test --format csv | tail -1 | cut -d, -f3)
echo "VM IP: ${VM_IP}"
```

---

## Step 2 — Mount the workspace into the VM

Mount the PoC repository so the VM can read the scripts and config:

```bash
multipass mount /home/<your-user>/Documents/GitHub/docs-search-prototype \
    opensearch-test:/home/ubuntu/docs-search-prototype
```

Verify:

```bash
multipass exec opensearch-test -- ls /home/ubuntu/docs-search-prototype/
```

---

## Step 3 — Bootstrap the host environment inside the VM

This installs LXD + Juju, tunes the kernel for OpenSearch, and bootstraps a
Juju controller:

```bash
multipass exec opensearch-test -- bash -c '
    cd /home/ubuntu/docs-search-prototype &&
    chmod +x bootstrap-env.sh scripts/*.sh &&
    bash bootstrap-env.sh
'
```

**What this does:**
- Installs `lxd` and `juju` snaps (if missing).
- Writes OpenSearch-required sysctl params to `/etc/sysctl.d/opensearch.conf`.
- Runs `lxd init --auto` and `juju bootstrap localhost lxd-controller`.

**Expected output:**
```
[bootstrap] lxd already installed.
[bootstrap] juju already installed.
[bootstrap] Writing host sysctl to /etc/sysctl.d/opensearch.conf...
[bootstrap] LXD already initialised.
[bootstrap] Juju controller 'lxd-controller' already exists.
[bootstrap] Bootstrap complete.
```

---

## Step 4 — Install Terraform inside the VM

Terraform is not included in `bootstrap-env.sh` (it's not a snap on all
platforms). Install it inside the VM:

```bash
multipass exec opensearch-test -- sudo snap install terraform --classic
```

Verify:

```bash
multipass exec opensearch-test -- terraform version
```

---

## Step 5 — Deploy OpenSearch via Terraform

The Terraform manifests deploy three charms: `opensearch`,
`self-signed-certificates` (required for TLS), and `data-integrator` (creates
the search index + credentials).

> **Important:** The upstream OpenSearch Terraform module and the workspace's
> `terraform/` directory must live on the VM's **local filesystem** (not the
> mounted volume) — the mount doesn't handle `.git` submodules inside
> `.terraform/` correctly. Copy the workspace to `/tmp` first:

```bash
multipass exec opensearch-test -- bash -c '
    rsync -a --exclude=".terraform" --exclude="*.tfstate*" \
        --exclude=".terraform.lock.hcl" \
        /home/ubuntu/docs-search-prototype/ /tmp/poc/ &&
    cd /tmp/poc/terraform &&
    terraform init &&
    terraform apply -auto-approve
'
```

**What this does:**
- Creates a `juju_model` named `sphinx-search` with `cloudinit-userdata` for
  in-container sysctl tuning.
- Deploys `opensearch` (1 unit, `profile=testing` = 1 GB heap).
- Deploys `self-signed-certificates` and wires the TLS integration.
- Deploys `data-integrator` (`index-name=sphinx-docs`, `extra-user-roles=admin`).
- Wires `data-integrator` ↔ `opensearch`.

**Expected output:**
```
Apply complete! Resources: 6 added, 0 changed, 0 destroyed.

Outputs:
data_integrator_app_name = "data-integrator"
index_name               = "sphinx-docs"
model_name               = "sphinx-search"
opensearch_app_name      = "opensearch"
```

Wait for all charms to become active (takes ~3–5 minutes):

```bash
multipass exec opensearch-test -- bash -c '
    juju status -m sphinx-search --format json 2>&1 | \
    jq -r ".applications | to_entries[] | \"\(.key): \(.value[\"units\"] | to_entries[] | .value[\"workload-status\"].current)\""
'
```

All three should report `active`:
```
data-integrator: active
opensearch: active
self-signed-certificates: active
```

---

## Step 6 — Fetch OpenSearch credentials

Run the credential extraction script, which calls the `data-integrator`
`get-credentials` Juju action and writes the endpoint, username, and password
to `.env`:

```bash
multipass exec opensearch-test -- bash -c '
    cd /tmp/poc && bash scripts/fetch-credentials.sh
'
```

**Expected output:**
```
[creds] Waiting for data-integrator to be active...
[creds] Running get-credentials on data-integrator/leader...
[creds] Writing scripts/../.env...
[creds] Done. Credentials written to scripts/../.env.
```

Verify the credentials (password redacted):

```bash
multipass exec opensearch-test -- bash -c '
    cat /tmp/poc/.env | grep -v PASSWORD
'
```

---

## Step 7 — Build the Kafka Operator docs

This clones the Kafka Operator repo, creates a docs venv, injects
`custom_search.js` into the Sphinx config, and builds both JSON (for
OpenSearch ingestion) and dirhtml (for the UI):

```bash
multipass exec opensearch-test -- bash -c '
    sudo apt-get update -qq &&
    sudo apt-get install -y -qq python3.12-venv &&
    cd /tmp/poc && bash scripts/build-docs.sh
'
```

**What this does:**
- Clones `canonical/kafka-operator` into `vendor/` (full clone — shallow
  clones break `sphinx_last_updated_by_git`).
- Creates a venv at `vendor/kafka-operator/docs/.venv` and installs
  `docs/requirements.txt`.
- Copies `static/custom_search.js` into `docs/_static/` and appends it to
  `html_js_files` in `conf.py`.
- Patches `conf.py` to work around a `sphinxext.opengraph` `KeyError('pagename')`
  bug with Sphinx 7.4.
- Runs `sphinx-build -b json` → `_build/json/` (51 `.fjson` files).
- Runs `sphinx-build -b dirhtml` → `_build/dirhtml/` (51 HTML pages).

**Expected output (tail):**
```
[docs] Building JSON output (for OpenSearch ingestion)...
build succeeded.
[docs] Building dirhtml output (for the UI)...
build succeeded.
[docs] Done.
```

---

## Step 8 — Index the docs into OpenSearch

Install the PoC Python dependencies and run the indexer:

```bash
multipass exec opensearch-test -- bash -c '
    cd /tmp/poc &&
    python3 -m venv .venv &&
    .venv/bin/pip install -q -r requirements.txt &&
    .venv/bin/python indexer.py
'
```

**Expected output:**
```
Deleting existing index 'sphinx-docs'...
Creating index 'sphinx-docs'...
Indexing .fjson files from vendor/kafka-operator/docs/_build/json...
Done. Indexed 41 documents; index now holds 41 docs.
```

---

## Step 9 — Start the FastAPI server

Start the FastAPI app, binding to `0.0.0.0` so it's reachable from the host:

```bash
multipass exec opensearch-test -- bash -c '
    cd /tmp/poc && .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
' &
```

> The `&` backgrounds the process so you keep your terminal. The server runs
> until you stop it or the VM shuts down.

Verify it's running (from inside the VM):

```bash
multipass exec opensearch-test -- curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
# → 200
```

---

## Step 10 — Access the Docs UI from the host laptop

The FastAPI server is bound to `0.0.0.0:8000` inside the VM, and Multipass
bridges the VM's network to the host. You can access it directly.

### Get the VM's IP

```bash
VM_IP=$(multipass info opensearch-test --format csv | tail -1 | cut -d, -f3)
echo "http://${VM_IP}:8000"
```

### Open in your browser

Navigate to:

```
http://<VM_IP>:8000
```

You'll see the Charmed Apache Kafka documentation with the sidebar search box.
Type a query (e.g. `broker`, `tls`, `connect`) and press Enter — the custom
JavaScript intercepts the form submission, calls `/api/search`, and renders
OpenSearch results in the **main content area** (replacing the page's content
with a results list). The sidebar nav menu stays visible and usable. Click the
**×** button in the results header or press **Esc** to restore the original
page content.

### Test the API from the host terminal

```bash
curl "http://${VM_IP}:8000/api/search?q=broker" | jq '.[0:2]'
```

**Expected output:**
```json
[
  {
    "title": "Apache Kafka listeners",
    "url": "/reference/listeners/",
    "snippet": "Apache Kafka listeners ¶ Charmed Apache Kafka comes with a set of listeners...",
    "score": 1.47
  },
  ...
]
```

---

## Step 11 — Run the test suite (optional)

Validate the full stack with the automated tests:

```bash
multipass exec opensearch-test -- bash -c '
    cd /tmp/poc &&
    .venv/bin/playwright install chromium &&
    .venv/bin/playwright install-deps chromium &&
    .venv/bin/python -m pytest tests/ -v
'
```

**Expected output:**
```
tests/test_frontend.py::test_search_form_hits_opensearch_endpoint[chromium] PASSED
tests/test_poc.py::test_search_zookeeper_returns_real_kafka_docs              PASSED
tests/test_poc.py::test_search_broker_returns_results                         PASSED
tests/test_poc.py::test_search_works_even_without_searchindex                  PASSED

4 passed in 2.69s
```

The negation test (`test_search_works_even_without_searchindex`) deletes
`searchindex.js`, asserts it 404s, and confirms `/api/search` still returns
results — proving search is powered exclusively by OpenSearch.

---

## Quick reference — common commands

| Action | Command |
|--------|---------|
| Start the VM | `multipass start opensearch-test` |
| Get the VM IP | `multipass info opensearch-test --format csv \| tail -1 \| cut -d, -f3` |
| Open a shell in the VM | `multipass shell opensearch-test` |
| Check Juju status | `multipass exec opensearch-test -- juju status -m sphinx-search` |
| Check FastAPI is running | `curl -s -o /dev/null -w "%{http_code}" http://<VM_IP>:8000/` |
| Search via API | `curl "http://<VM_IP>:8000/api/search?q=broker" \| jq` |
| Stop the VM | `multipass stop opensearch-test` |

---

## Troubleshooting

### `terraform init` fails with "no available releases match ~> 1.0, ~> 2.0"

The upstream OpenSearch module pins `juju ~> 1.0` in its `versions.tf`. Ensure
`terraform/versions.tf` also pins `~> 1.0` (not `~> 2.0`):

```bash
multipass exec opensearch-test -- bash -c '
    cd /tmp/poc/terraform &&
    sed -i "s/~> 2.0/~> 1.0/" versions.tf &&
    rm -f .terraform.lock.hcl &&
    terraform init
'
```

### `juju_integration` fails with "application has no 'opensearch-client' relation"

The `data-integrator` charm's requires endpoint is `opensearch` (not
`opensearch-client`). OpenSearch's provides endpoint is `opensearch-client`.
Check `terraform/main.tf`:

```hcl
application {
    name     = juju_application.data_integrator.name
    endpoint = "opensearch"           # data-integrator side
}
application {
    name     = module.opensearch.app_names["opensearch"]
    endpoint = "opensearch-client"     # opensearch side
}
```

### Sphinx build fails with `KeyError: 'pagename'`

This is a `sphinxext.opengraph 0.13.0` + Sphinx 7.4 incompatibility.
`build-docs.sh` patches `conf.py` automatically. If it still fails, verify
the patch was applied:

```bash
multipass exec opensearch-test -- grep _poc_ogp_fix /tmp/poc/vendor/kafka-operator/docs/conf.py
```

### Sphinx build fails with "Git clone too shallow"

`build-docs.sh` uses a full clone (not `--depth 1`). If you modified the
script, ensure the clone command doesn't include `--depth 1`.

### `python3 -m venv` fails with "ensurepip is not available"

Install the venv package:

```bash
multipass exec opensearch-test -- sudo apt-get install -y python3.12-venv
```

### Playwright fails with "Target page, context or browser has been closed"

Install system dependencies:

```bash
multipass exec opensearch-test -- bash -c '
    sudo apt-get update -o Acquire::ForceIPv4=true &&
    cd /tmp/poc && .venv/bin/playwright install-deps chromium
'
```

### OpenSearch charm stuck in `blocked` with "vm.swappiness should be 0"

The host sysctl params weren't applied. Re-run `bootstrap-env.sh` or apply
manually:

```bash
multipass exec opensearch-test -- bash -c '
    sudo tee /etc/sysctl.d/opensearch.conf <<EOF
vm.max_map_count   = 262144
vm.swappiness      = 0
net.ipv4.tcp_retries2 = 5
fs.file-max        = 1048576
EOF
    sudo sysctl -p /etc/sysctl.d/opensearch.conf
'
```

### Can't access the UI from the host

1. Verify the VM is running: `multipass info opensearch-test`
2. Verify FastAPI is bound to `0.0.0.0` (not `127.0.0.1`):
   ```bash
   multipass exec opensearch-test -- ss -tlnp | grep 8000
   ```
   You should see `0.0.0.0:8000`, not `127.0.0.1:8000`.
3. Verify the VM IP is correct: `multipass info opensearch-test`
4. Test from the host: `curl -v http://<VM_IP>:8000/`

---

## Architecture recap

```
Host laptop
  └─ Browser → http://<VM_IP>:8000
       │
       ▼
Multipass VM (opensearch-test)
  ├─ FastAPI (:8000, bound to 0.0.0.0)
  │    ├─ /            → serves Sphinx dirhtml docs
  │    └─ /api/search  → queries OpenSearch
  │
  ├─ OpenSearch (Juju/LXD, :9200)
  │    └─ sphinx-docs index (41 documents)
  │
  └─ data-integrator → provides credentials via get-credentials action
```

OpenSearch credentials live only in `.env` inside the VM — they never reach
the browser. The FastAPI proxy is the sole client of OpenSearch.
