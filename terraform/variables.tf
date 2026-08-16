# PoC-wide variables.

variable "model_name" {
  type        = string
  description = "Name of the Juju model that hosts the OpenSearch deployment."
  default     = "sphinx-search"
}

variable "opensearch_channel" {
  type        = string
  description = "Charmhub channel for the opensearch machine charm."
  default     = "2/stable"
}

variable "opensearch_units" {
  type        = number
  description = "Number of OpenSearch units. 1 is enough for a local PoC."
  default     = 1
}

variable "data_integrator_channel" {
  type        = string
  description = "Charmhub channel for the data-integrator charm."
  default     = "latest/stable"
}

variable "index_name" {
  type        = string
  description = "OpenSearch index created by data-integrator and used by indexer.py."
  default     = "sphinx-docs"
}
