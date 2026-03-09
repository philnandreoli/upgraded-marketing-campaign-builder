terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Service Bus Namespace
# ---------------------------------------------------------------------------

resource "azurerm_servicebus_namespace" "this" {
  name                = "sb-${var.environment}-marketing"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Workflow Jobs Queue
# ---------------------------------------------------------------------------

resource "azurerm_servicebus_queue" "workflow_jobs" {
  name         = var.queue_name
  namespace_id = azurerm_servicebus_namespace.this.id

  lock_duration                        = var.queue_lock_duration
  default_message_ttl                  = var.queue_message_ttl
  max_delivery_count                   = var.queue_max_delivery_count
  max_size_in_megabytes                = var.queue_max_size_mb
  dead_lettering_on_message_expiration = var.enable_dead_lettering_on_message_expiration
}

# ---------------------------------------------------------------------------
# Private endpoint — only for Premium SKU with private networking enabled
# ---------------------------------------------------------------------------

resource "azurerm_private_endpoint" "service_bus" {
  count               = (var.enable_private_networking && var.sku == "Premium") ? 1 : 0
  name                = "pe-${var.environment}-servicebus"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-${var.environment}-servicebus"
    private_connection_resource_id = azurerm_servicebus_namespace.this.id
    subresource_names              = ["namespace"]
    is_manual_connection           = false
  }

  dynamic "private_dns_zone_group" {
    for_each = var.private_dns_zone_id != null ? [1] : []
    content {
      name                 = "dns-zone-group-servicebus"
      private_dns_zone_ids = [var.private_dns_zone_id]
    }
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Diagnostic settings
# ---------------------------------------------------------------------------

resource "azurerm_monitor_diagnostic_setting" "service_bus" {
  count                      = var.log_analytics_workspace_id != null ? 1 : 0
  name                       = "diag-${var.environment}-servicebus"
  target_resource_id         = azurerm_servicebus_namespace.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "OperationalLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}
