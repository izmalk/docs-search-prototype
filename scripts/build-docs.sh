#!/usr/bin/env bash
# Phase 3: Clone the Canonical Kafka Operator docs and build them in both
# JSON (for OpenSearch ingestion) and dirhtml (for the FastAPI-served UI).
#
# Output:
#   vendor/kafka-operator/docs/_build/json/   <- .fjson files for indexer.py
#   vendor/kafka-operator/docs/_build/dirhtml/ <- served by app.py
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="${VENDOR_DIR:-${REPO_ROOT}/vendor}"
KAFKA_REPO="${KAFKA_REPO:-https://github.com/canonical/kafka-operator.git}"
KAFKA_DIR="${VENDOR}/kafka-operator"
DOCS_DIR="${KAFKA_DIR}/docs"

log() { printf '\033[1;34m[docs]\033[0m %s\n' "$*"; }

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1"; exit 1; }; }
require_cmd git
require_cmd python3

# --- 1. Clone / update -----------------------------------------------------
if [ ! -d "${KAFKA_DIR}" ]; then
    log "Cloning kafka-operator into ${VENDOR}/..."
    mkdir -p "${VENDOR}"
    # Full clone (not --depth 1): sphinx_last_updated_by_git needs git history.
    git clone "${KAFKA_REPO}" "${KAFKA_DIR}"
else
    log "kafka-operator already present."
fi

# --- 2. Docs venv + dependencies ------------------------------------------
cd "${DOCS_DIR}"
log "Creating docs venv (.venv) and installing requirements.txt..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# --- 3. Inject custom_search.js ------------------------------------------
# Idempotently place our JS in _static and append it to html_js_files in conf.py
# so it is loaded on every page. We patch conf.py in place on every run because
# the kafka-operator repo is a throwaway clone.
log "Injecting custom_search.js into conf.py..."
mkdir -p _static
cp "${REPO_ROOT}/static/custom_search.js" _static/custom_search.js

if ! grep -q 'custom_search.js' conf.py; then
    # Append to the existing html_js_files list (conf.py defines it ~line 248).
    python3 - <<'PY'
import re, pathlib
p = pathlib.Path("conf.py")
src = p.read_text()
# Insert into the html_js_files list; if not found, define it.
if "html_js_files" in src:
    src = re.sub(
        r'(html_js_files\s*=\s*\[)([^\]]*?)\]',
        lambda m: m.group(1) + m.group(2) + (",\n" if m.group(2).strip() and not m.group(2).rstrip().endswith(",") else "") + '    "custom_search.js",\n]',
        src,
        count=1,
    )
else:
    src += '\nhtml_js_files = ["custom_search.js"]\n'
p.write_text(src)
PY
fi

# Work around sphinxext-opengraph 0.13.0 KeyError('pagename') with Sphinx 7.4:
# the extension accesses context['pagename'] but the canonical_sphinx theme
# doesn't always populate it. We add a conf.py setup() that connects a
# html-page-context handler with higher priority (runs first) to inject it.
python3 - <<'PY'
import pathlib
p = pathlib.Path("conf.py")
src = p.read_text()
patch = '''

# --- PoC patch: fix sphinxext-opengraph KeyError('pagename') ---
def _poc_ogp_fix(app, pagename, templatename, context, doctree):
    if "pagename" not in context:
        context["pagename"] = pagename

def setup(app):
    # Priority -200 ensures we run before sphinxext.opengraph (default 500).
    app.connect("html-page-context", _poc_ogp_fix, priority=-200)
'''
if "_poc_ogp_fix" not in src:
    p.write_text(src + patch)
PY

# --- 4. Build JSON + dirhtml ---------------------------------------------
SPHINX_OPTS="-c . -d _dev/.doctrees -j auto"

log "Building JSON output (for OpenSearch ingestion)..."
sphinx-build -b json . _build/json ${SPHINX_OPTS} 2>&1 | tail -5

log "Building dirhtml output (for the UI)..."
sphinx-build -b dirhtml . _build/dirhtml ${SPHINX_OPTS} 2>&1 | tail -5

log "Done. Outputs:"
log "  ${DOCS_DIR}/_build/json   (.fjson for indexer.py)"
log "  ${DOCS_DIR}/_build/dirhtml (served by app.py)"
