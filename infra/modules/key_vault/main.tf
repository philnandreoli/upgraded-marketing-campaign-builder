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

data "azurerm_client_config" "current" {}

# ---------------------------------------------------------------------------
# Key Vault (RBAC authorization model)
# ---------------------------------------------------------------------------

# Key Vault names must be globally unique and 3-24 alphanumeric/hyphen characters.
resource "random_id" "kv_suffix" {
  byte_length = 3
}

resource "azurerm_key_vault" "this" {
  name                       = "kv-${var.environment}-mkt-${random_id.kv_suffix.hex}"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  tenant_id                  = var.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = var.soft_delete_retention_days
  purge_protection_enabled   = var.purge_protection_enabled
  tags                       = var.tags

  network_acls {
    default_action = var.enable_private_networking ? "Deny" : "Allow"
    bypass         = "AzureServices"
  }
}

# ---------------------------------------------------------------------------
# Private endpoint
# ---------------------------------------------------------------------------

resource "azurerm_private_endpoint" "key_vault" {
  count               = var.enable_private_networking ? 1 : 0
  name                = "pe-${var.environment}-keyvault"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-${var.environment}-keyvault"
    private_connection_resource_id = azurerm_key_vault.this.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  dynamic "private_dns_zone_group" {
    for_each = var.private_dns_zone_id != null ? [1] : []
    content {
      name                 = "dns-zone-group-keyvault"
      private_dns_zone_ids = [var.private_dns_zone_id]
    }
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Diagnostic settings
# ---------------------------------------------------------------------------

resource "azurerm_monitor_diagnostic_setting" "key_vault" {
  count                      = var.log_analytics_workspace_id != null ? 1 : 0
  name                       = "diag-${var.environment}-keyvault"
  target_resource_id         = azurerm_key_vault.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "AuditEvent"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
