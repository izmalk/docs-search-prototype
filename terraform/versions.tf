terraform {
  required_version = ">= 1.6"

  required_providers {
    juju = {
      source  = "juju/juju"
      # v1.x — matches the upstream opensearch-operator simple_deployment
      # module (rev349), which pins ~> 1.0 but uses model_uuid (a v2-style
      # attribute that v1.5+ also accepts).
      version = "~> 1.0"
    }
  }
}
