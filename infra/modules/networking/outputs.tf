output "vnet_id" {
  description = "Resource ID of the virtual network."
  value       = azurerm_virtual_network.this.id
}

output "vnet_name" {
  description = "Name of the virtual network."
  value       = azurerm_virtual_network.this.name
}

output "container_apps_subnet_id" {
  description = "Resource ID of the Container Apps delegated subnet."
  value       = azurerm_subnet.container_apps.id
}

output "postgresql_subnet_id" {
  description = "Resource ID of the PostgreSQL delegated subnet."
  value       = azurerm_subnet.postgresql.id
}

output "private_endpoints_subnet_id" {
  description = "Resource ID of the private endpoints subnet."
  value       = azurerm_subnet.private_endpoints.id
}

output "postgresql_private_dns_zone_id" {
  description = "Resource ID of the PostgreSQL private DNS zone. Null when private networking is disabled."
  value       = var.enable_private_networking ? azurerm_private_dns_zone.postgresql[0].id : null
}

output "service_bus_private_dns_zone_id" {
  description = "Resource ID of the Service Bus private DNS zone. Null when private networking is disabled."
  value       = var.enable_private_networking ? azurerm_private_dns_zone.service_bus[0].id : null
}

output "key_vault_private_dns_zone_id" {
  description = "Resource ID of the Key Vault private DNS zone. Null when private networking is disabled."
  value       = var.enable_private_networking ? azurerm_private_dns_zone.key_vault[0].id : null
}

output "acr_private_dns_zone_id" {
  description = "Resource ID of the ACR private DNS zone. Null when private networking is disabled."
  value       = var.enable_private_networking ? azurerm_private_dns_zone.acr[0].id : null
}
