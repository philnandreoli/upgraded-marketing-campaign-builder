output "app_configuration_id" {
  description = "Resource ID of the App Configuration store."
  value       = azurerm_app_configuration.this.id
}

output "app_configuration_name" {
  description = "Name of the App Configuration store."
  value       = azurerm_app_configuration.this.name
}

output "app_configuration_endpoint" {
  description = "Endpoint URL of the App Configuration store. Set as AZURE_APP_CONFIGURATION_ENDPOINT in container apps."
  value       = azurerm_app_configuration.this.endpoint
}
