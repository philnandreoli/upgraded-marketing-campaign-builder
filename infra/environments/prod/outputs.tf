output "resource_group_name" {
  description = "Name of the deployed resource group."
  value       = azurerm_resource_group.this.name
}

output "resource_group_id" {
  description = "Resource ID of the deployed resource group."
  value       = azurerm_resource_group.this.id
}

output "acr_login_server" {
  description = "Login server URL of the Azure Container Registry."
  value       = module.container_registry.acr_login_server
}

output "acr_name" {
  description = "Name of the Azure Container Registry."
  value       = module.container_registry.acr_name
}

output "container_apps_environment_id" {
  description = "Resource ID of the Container Apps Environment."
  value       = module.container_apps.container_apps_environment_id
}

output "frontend_app_fqdn" {
  description = "FQDN of the Frontend Container App."
  value       = module.container_apps.frontend_app_fqdn
}

output "api_app_fqdn" {
  description = "FQDN of the API Container App."
  value       = module.container_apps.api_app_fqdn
}

output "postgresql_fqdn" {
  description = "FQDN of the PostgreSQL Flexible Server."
  value       = module.postgresql.postgresql_fqdn
}

output "postgresql_database_name" {
  description = "Name of the application database."
  value       = module.postgresql.postgresql_database_name
}

output "service_bus_namespace_fqdn" {
  description = "FQDN of the Service Bus namespace."
  value       = module.service_bus.service_bus_namespace_fqdn
}

output "service_bus_queue_name" {
  description = "Name of the Service Bus workflow queue."
  value       = module.service_bus.service_bus_queue_name
}

output "key_vault_uri" {
  description = "URI of the Key Vault."
  value       = module.key_vault.key_vault_uri
}

output "application_insights_connection_string" {
  description = "Application Insights connection string."
  value       = module.monitoring.application_insights_connection_string
  sensitive   = true
}

output "api_identity_client_id" {
  description = "Client ID of the API managed identity."
  value       = module.identities.api_identity_client_id
}

output "worker_identity_client_id" {
  description = "Client ID of the Worker managed identity."
  value       = module.identities.worker_identity_client_id
}

output "migration_identity_client_id" {
  description = "Client ID of the migration managed identity."
  value       = module.identities.migration_identity_client_id
}

output "migration_job_name" {
  description = "Name of the Migration Container Apps Job."
  value       = module.container_apps.migration_job_name
}

output "log_analytics_workspace_id" {
  description = "Resource ID of the Log Analytics workspace."
  value       = module.monitoring.log_analytics_workspace_id
}
