output "postgresql_server_id" {
  description = "Resource ID of the PostgreSQL Flexible Server."
  value       = azurerm_postgresql_flexible_server.this.id
}

output "postgresql_server_name" {
  description = "Name of the PostgreSQL Flexible Server."
  value       = azurerm_postgresql_flexible_server.this.name
}

output "postgresql_fqdn" {
  description = "Fully qualified domain name of the PostgreSQL Flexible Server."
  value       = azurerm_postgresql_flexible_server.this.fqdn
}

output "postgresql_database_name" {
  description = "Name of the application database."
  value       = azurerm_postgresql_flexible_server_database.app.name
}

output "administrator_login" {
  description = "Local administrator login name."
  value       = var.password_auth_enabled ? var.administrator_login : null
}

output "administrator_password" {
  description = "Generated local administrator password (if applicable)."
  value       = var.password_auth_enabled && var.administrator_password == null ? random_password.pg_admin[0].result : null
  sensitive   = true
}
