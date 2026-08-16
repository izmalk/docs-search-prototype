# Phase 2: Declaratively deploy Charmed OpenSearch + data-integrator on LXD.
#
# The upstream opensearch-operator simple_deployment module already deploys
# `opensearch`, `self-signed-certificates`, and the TLS integration between them.
# We add `data-integrator` (for index creation + credential generation) and
# wire it to OpenSearch's `opensearch-client` endpoint.

# The Juju model owns the cloudinit-userdata that applies the OpenSearch
# sysctl requirements inside every new LXD container.
resource "juju_model" "sphinx_search" {
  name = var.model_name

  config = {
    logging-config               = "<root>=INFO;unit=DEBUG"
    update-status-hook-interval  = "5m"
    cloudinit-userdata           = <<-EOT
      postruncmd:
        - [ 'sysctl', '-w', 'vm.max_map_count=262144' ]
        - [ 'sysctl', '-w', 'fs.file-max=1048576' ]
        - [ 'sysctl', '-w', 'vm.swappiness=0' ]
        - [ 'sysctl', '-w', 'net.ipv4.tcp_retries2=5' ]
    EOT
  }
}

# Reuse Canonical's official OpenSearch Terraform module.
# It deploys opensearch + self-signed-certificates and the TLS integration.
module "opensearch" {
  source = "git::https://github.com/canonical/opensearch-operator.git//terraform/charm/simple_deployment?ref=rev349"

  model_uuid = juju_model.sphinx_search.uuid
  app_name   = "opensearch"
  channel    = var.opensearch_channel
  units      = var.opensearch_units
  # `testing` profile = 1 GB heap (vs. 50% of RAM in production).
  # init_hold=false lets the cluster form immediately (the module sets this on
  # main orchestrators; we pass it explicitly for clarity).
  config = {
    profile   = "testing"
    init_hold = "false"
  }
}

# data-integrator: creates the `sphinx-docs` index and an admin user whose
# credentials are fetched via the `get-credentials` Juju action.
resource "juju_application" "data_integrator" {
  name = "data-integrator"

  model_uuid = juju_model.sphinx_search.uuid

  charm {
    name    = "data-integrator"
    channel = var.data_integrator_channel
  }

  config = {
    index-name        = var.index_name
    extra-user-roles  = "admin"
  }
}

# Wire data-integrator to OpenSearch so the index + credentials are provisioned.
resource "juju_integration" "data_integrator_opensearch" {
  model_uuid = juju_model.sphinx_search.uuid

  application {
    name     = juju_application.data_integrator.name
    endpoint = "opensearch"          # data-integrator requires `opensearch`
  }

  application {
    name     = module.opensearch.app_names["opensearch"]
    endpoint = "opensearch-client"    # opensearch provides `opensearch-client`
  }

  depends_on = [module.opensearch, juju_application.data_integrator]
}
