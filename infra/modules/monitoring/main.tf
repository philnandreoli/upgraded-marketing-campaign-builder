terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Log Analytics Workspace
# ---------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "this" {
  name                = "law-${var.environment}-marketing"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.log_analytics_retention_days
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Application Insights (workspace-based)
# ---------------------------------------------------------------------------

resource "azurerm_application_insights" "this" {
  name                = "appi-${var.environment}-marketing"
  resource_group_name = var.resource_group_name
  location            = var.location
  workspace_id        = azurerm_log_analytics_workspace.this.id
  application_type    = "web"
  sampling_percentage = var.app_insights_sampling_percentage
  tags                = var.tags
}
