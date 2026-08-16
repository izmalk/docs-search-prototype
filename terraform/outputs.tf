output "model_name" {
  description = "Juju model hosting the OpenSearch deployment."
  value       = juju_model.sphinx_search.name
}

output "opensearch_app_name" {
  description = "Name of the OpenSearch application (for juju status / actions)."
  value       = module.opensearch.app_names["opensearch"]
}

output "data_integrator_app_name" {
  description = "Name of the data-integrator application (run get-credentials on it)."
  value       = juju_application.data_integrator.name
}

output "index_name" {
  description = "OpenSearch index created by data-integrator."
  value       = var.index_name
}
