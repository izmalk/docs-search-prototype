#!/usr/bin/env bash
# Phase 1: Environment bootstrap for the OpenSearch-backed Sphinx search PoC.
#
# Idempotently:
#   1. Ensures prerequisites (lxd + juju snaps, ~/.local/share for Juju 3.x).
#   2. Writes the host kernel parameters OpenSearch requires.
#   3. Initialises LXD and bootstraps a local Juju controller.
#
# The Juju model itself is NOT created here — Terraform owns it (Phase 2).
set -euo pipefail

CONTROLLER_NAME="${JUJU_CONTROLLER:-lxd-controller}"
SYSCTL_CONF="/etc/sysctl.d/opensearch.conf"

log() { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[bootstrap]\033[0m %s\n' "$*" >&2; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || { err "Missing required command: $1"; exit 1; }
}

ensure_snap() {
    local pkg=$1
    if ! snap list "$pkg" >/dev/null 2>&1; then
        log "Installing $pkg via snap..."
        sudo snap install "$pkg"
    else
        log "$pkg already installed."
    fi
}

# --- 1. Prerequisites -----------------------------------------------------
require_cmd snap
ensure_snap lxd
ensure_snap juju

# Juju 3.x is strictly confined and cannot create ~/.local/share itself.
mkdir -p "${HOME}/.local/share"

# --- 2. Host kernel parameters -------------------------------------------
# OpenSearch refuses to become active without these. LXD containers share the
# host kernel, so the host must be tuned in addition to the model's
# cloudinit-userdata (handled in Terraform).
log "Writing host sysctl to ${SYSCTL_CONF}..."
sudo tee "${SYSCTL_CONF}" >/dev/null <<'EOF'
# Required by Charmed OpenSearch (see opensearch-operator docs).
vm.max_map_count   = 262144
vm.swappiness      = 0
net.ipv4.tcp_retries2 = 5
fs.file-max        = 1048576
EOF
sudo sysctl -p "${SYSCTL_CONF}"

# --- 3. LXD + Juju controller --------------------------------------------
if ! lxc list >/dev/null 2>&1; then
    log "Initialising LXD with defaults..."
    lxd init --auto
else
    log "LXD already initialised."
fi

if juju controllers --format json 2>/dev/null | jq -e ".controllers[\"${CONTROLLER_NAME}\"]" >/dev/null 2>&1; then
    log "Juju controller '${CONTROLLER_NAME}' already exists."
else
    log "Bootstrapping Juju controller '${CONTROLLER_NAME}' on LXD..."
    juju bootstrap localhost "${CONTROLLER_NAME}"
fi

log "Bootstrap complete. Next: cd terraform && terraform init && terraform apply"
