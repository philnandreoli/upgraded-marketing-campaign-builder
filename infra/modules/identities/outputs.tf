output "api_identity_id" {
  description = "Resource ID of the API managed identity."
  value       = azurerm_user_assigned_identity.api.id
}

output "api_identity_client_id" {
  description = "Client ID of the API managed identity."
  value       = azurerm_user_assigned_identity.api.client_id
}

output "api_identity_principal_id" {
  description = "Principal ID of the API managed identity."
  value       = azurerm_user_assigned_identity.api.principal_id
}

output "worker_identity_id" {
  description = "Resource ID of the Worker managed identity."
  value       = azurerm_user_assigned_identity.worker.id
}

output "worker_identity_client_id" {
  description = "Client ID of the Worker managed identity."
  value       = azurerm_user_assigned_identity.worker.client_id
}

output "worker_identity_principal_id" {
  description = "Principal ID of the Worker managed identity."
  value       = azurerm_user_assigned_identity.worker.principal_id
}

output "migration_identity_id" {
  description = "Resource ID of the migration managed identity."
  value       = azurerm_user_assigned_identity.migration.id
}

output "migration_identity_client_id" {
  description = "Client ID of the migration managed identity."
  value       = azurerm_user_assigned_identity.migration.client_id
}

output "migration_identity_principal_id" {
  description = "Principal ID of the migration managed identity."
  value       = azurerm_user_assigned_identity.migration.principal_id
}
