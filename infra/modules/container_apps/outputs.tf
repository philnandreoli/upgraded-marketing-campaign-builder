output "container_apps_environment_id" {
  description = "Resource ID of the Container Apps Environment."
  value       = azurerm_container_app_environment.this.id
}

output "container_apps_environment_name" {
  description = "Name of the Container Apps Environment."
  value       = azurerm_container_app_environment.this.name
}

output "container_apps_environment_default_domain" {
  description = "Default domain of the Container Apps Environment."
  value       = azurerm_container_app_environment.this.default_domain
}

output "frontend_app_id" {
  description = "Resource ID of the Frontend Container App."
  value       = azurerm_container_app.frontend.id
}

output "frontend_app_fqdn" {
  description = "FQDN of the Frontend Container App ingress."
  value       = azurerm_container_app.frontend.ingress[0].fqdn
}

output "api_app_id" {
  description = "Resource ID of the API Container App."
  value       = azurerm_container_app.api.id
}

output "api_app_fqdn" {
  description = "FQDN of the API Container App ingress."
  value       = azurerm_container_app.api.ingress[0].fqdn
}

output "worker_app_id" {
  description = "Resource ID of the Worker Container App."
  value       = azurerm_container_app.worker.id
}

output "migration_job_id" {
  description = "Resource ID of the Migration Container Apps Job."
  value       = azurerm_container_app_job.migration.id
}

output "migration_job_name" {
  description = "Name of the Migration Container Apps Job."
  value       = azurerm_container_app_job.migration.name
}
