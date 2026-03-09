terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Random password for local admin (used only when password_auth_enabled=true)
# ---------------------------------------------------------------------------

resource "random_password" "pg_admin" {
  count   = var.password_auth_enabled && var.administrator_password == null ? 1 : 0
  length  = 32
  special = true
}

locals {
  pg_admin_password = var.administrator_password != null ? var.administrator_password : (
    var.password_auth_enabled ? random_password.pg_admin[0].result : null
  )
}

# ---------------------------------------------------------------------------
# PostgreSQL Flexible Server
# ---------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server" "this" {
  name                         = "psql-${var.environment}-marketing"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  version                      = var.postgresql_version
  sku_name                     = var.sku_name
  storage_mb                   = var.storage_mb
  backup_retention_days        = var.backup_retention_days
  geo_redundant_backup_enabled = var.geo_redundant_backup

  # Entra authentication
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = var.password_auth_enabled
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  # Local admin (only meaningful when password_auth_enabled = true)
  administrator_login    = var.password_auth_enabled ? var.administrator_login : null
  administrator_password = var.password_auth_enabled ? local.pg_admin_password : null

  # High availability
  dynamic "high_availability" {
    for_each = var.ha_mode != "Disabled" ? [1] : []
    content {
      mode = var.ha_mode
    }
  }

  # VNet integration (private access)
  delegated_subnet_id = var.enable_private_networking ? var.delegated_subnet_id : null
  private_dns_zone_id = var.enable_private_networking ? var.private_dns_zone_id : null

  tags = var.tags
}

data "azurerm_client_config" "current" {}

# ---------------------------------------------------------------------------
# Entra admin
# ---------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "this" {
  server_name         = azurerm_postgresql_flexible_server.this.name
  resource_group_name = var.resource_group_name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = var.entra_admin_object_id
  principal_name      = var.entra_admin_principal_name
  principal_type      = "User"
}

# ---------------------------------------------------------------------------
# Application database
# ---------------------------------------------------------------------------

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.this.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

# ---------------------------------------------------------------------------
# Diagnostic settings
# ---------------------------------------------------------------------------

resource "azurerm_monitor_diagnostic_setting" "postgresql" {
  count                      = var.log_analytics_workspace_id != null ? 1 : 0
  name                       = "diag-${var.environment}-postgresql"
  target_resource_id         = azurerm_postgresql_flexible_server.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "PostgreSQLLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
