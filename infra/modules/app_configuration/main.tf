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

# App Configuration store names must be globally unique and 5-50 alphanumeric/hyphen characters.
resource "random_id" "appcs_suffix" {
  byte_length = 3
}

# ---------------------------------------------------------------------------
# Azure App Configuration store
# ---------------------------------------------------------------------------

resource "azurerm_app_configuration" "this" {
  name                       = "appcs-${var.environment}-marketing-${random_id.appcs_suffix.hex}"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  sku                        = var.sku
  public_network_access      = var.enable_private_networking ? "Disabled" : "Enabled"
  local_auth_enabled         = false
  soft_delete_retention_days = var.soft_delete_retention_days
  tags                       = var.tags
}

# ---------------------------------------------------------------------------
# Private endpoint (optional — enabled when enable_private_networking = true)
# ---------------------------------------------------------------------------

resource "azurerm_private_endpoint" "app_configuration" {
  count               = var.enable_private_networking ? 1 : 0
  name                = "pe-${var.environment}-appcs"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-${var.environment}-appcs"
    private_connection_resource_id = azurerm_app_configuration.this.id
    subresource_names              = ["configurationStores"]
    is_manual_connection           = false
  }

  dynamic "private_dns_zone_group" {
    for_each = var.private_dns_zone_id != null ? [1] : []
    content {
      name                 = "dns-zone-group-appcs"
      private_dns_zone_ids = [var.private_dns_zone_id]
    }
  }
}

# ---------------------------------------------------------------------------
# RBAC — App Configuration Data Reader for API, Worker, and Migration identities
#
# Data Reader is sufficient for reading key-values and resolving Key Vault
# references at runtime.  Write/owner access is not granted to workload
# identities; configuration management is performed by operators or CI/CD.
# ---------------------------------------------------------------------------

resource "azurerm_role_assignment" "api_appcs_data_reader" {
  scope                = azurerm_app_configuration.this.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = var.api_identity_principal_id
}

resource "azurerm_role_assignment" "worker_appcs_data_reader" {
  scope                = azurerm_app_configuration.this.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = var.worker_identity_principal_id
}

resource "azurerm_role_assignment" "migration_appcs_data_reader" {
  scope                = azurerm_app_configuration.this.id
  role_definition_name = "App Configuration Data Reader"
  principal_id         = var.migration_identity_principal_id
}

# ---------------------------------------------------------------------------
# Diagnostic settings (forwarded to Log Analytics)
# ---------------------------------------------------------------------------

resource "azurerm_monitor_diagnostic_setting" "app_configuration" {
  count                      = var.log_analytics_workspace_id != null ? 1 : 0
  name                       = "diag-${var.environment}-appcs"
  target_resource_id         = azurerm_app_configuration.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "HttpRequest"
  }

  enabled_log {
    category = "Audit"
  }

  metric {
    category = "AllMetrics"
  }
}
