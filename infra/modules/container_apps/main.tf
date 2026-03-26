terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

locals {
  # Build the workload_profile block only for non-Consumption profiles
  use_dedicated_profile = var.workload_profile_type != "Consumption"
  workload_profile_name = var.workload_profile_type != "Consumption" ? var.workload_profile_type : "Consumption"
}

# ---------------------------------------------------------------------------
# Container Apps Environment
# ---------------------------------------------------------------------------

resource "azurerm_container_app_environment" "this" {
  name                           = "cae-${var.environment}-marketing"
  resource_group_name            = var.resource_group_name
  location                       = var.location
  log_analytics_workspace_id     = var.log_analytics_workspace_id
  infrastructure_subnet_id       = var.infrastructure_subnet_id
  internal_load_balancer_enabled = var.internal_load_balancer_enabled

  dynamic "workload_profile" {
    for_each = local.use_dedicated_profile ? [1] : []
    content {
      name                  = local.workload_profile_name
      workload_profile_type = var.workload_profile_type
      minimum_count         = var.workload_profile_min_count
      maximum_count         = var.workload_profile_max_count
    }
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Frontend Container App (external HTTPS ingress)
# Uses the API identity for ACR pull — both already have AcrPull via identities module.
# ---------------------------------------------------------------------------

resource "azurerm_container_app" "frontend" {
  name                         = "ca-${var.environment}-frontend"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.api_identity_id]
  }

  template {
    min_replicas = var.frontend_min_replicas
    max_replicas = var.frontend_max_replicas

    container {
      name   = "frontend"
      image  = var.frontend_image
      cpu    = var.frontend_cpu
      memory = var.frontend_memory

      env {
        name  = "BACKEND_URL"
        value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
      }
    }
  }

  registry {
    server   = var.container_registry_server
    identity = var.api_identity_id
  }

  ingress {
    external_enabled = true
    target_port      = 80
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# ---------------------------------------------------------------------------
# API Container App
# ---------------------------------------------------------------------------

resource "azurerm_container_app" "api" {
  name                         = "ca-${var.environment}-api"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.api_identity_id]
  }

  template {
    min_replicas = var.api_min_replicas
    max_replicas = var.api_max_replicas

    container {
      name   = "api"
      image  = var.api_image
      cpu    = var.api_cpu
      memory = var.api_memory

      # Bootstrap — all runtime settings are loaded from Azure App Configuration
      # at startup using APP_ENV as the label selector.
      env {
        name  = "APP_ENV"
        value = var.environment
      }
      env {
        name  = "AZURE_APP_CONFIGURATION_ENDPOINT"
        value = var.azure_app_configuration_endpoint
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.api_identity_client_id
      }
      # Per-component identity override — each app uses its own managed identity
      # principal as the PostgreSQL user; this overrides any App Config value.
      env {
        name  = "AZURE_POSTGRES_USER"
        value = var.azure_postgres_user_api
      }
    }
  }

  registry {
    server   = var.container_registry_server
    identity = var.api_identity_id
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# ---------------------------------------------------------------------------
# Worker Container App
# ---------------------------------------------------------------------------

resource "azurerm_container_app" "worker" {
  name                         = "ca-${var.environment}-worker"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.worker_identity_id]
  }

  template {
    min_replicas = var.worker_min_replicas
    max_replicas = var.worker_max_replicas

    container {
      name   = "worker"
      image  = var.worker_image
      cpu    = var.worker_cpu
      memory = var.worker_memory

      # Bootstrap — all runtime settings are loaded from Azure App Configuration
      # at startup using APP_ENV as the label selector.
      env {
        name  = "APP_ENV"
        value = var.environment
      }
      env {
        name  = "AZURE_APP_CONFIGURATION_ENDPOINT"
        value = var.azure_app_configuration_endpoint
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.worker_identity_client_id
      }
      # Per-component identity override — each app uses its own managed identity
      # principal as the PostgreSQL user; this overrides any App Config value.
      env {
        name  = "AZURE_POSTGRES_USER"
        value = var.azure_postgres_user_worker
      }
    }
  }

  registry {
    server   = var.container_registry_server
    identity = var.worker_identity_id
  }
}

# ---------------------------------------------------------------------------
# Migration Container Apps Job (manual trigger)
# ---------------------------------------------------------------------------

resource "azurerm_container_app_job" "migration" {
  name                         = "caj-${var.environment}-migration"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = azurerm_container_app_environment.this.id
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.migration_identity_id]
  }

  replica_timeout_in_seconds = 600
  replica_retry_limit        = 1

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name   = "migration"
      image  = var.migration_image
      cpu    = var.migration_cpu
      memory = var.migration_memory

      # Bootstrap — all runtime settings are loaded from Azure App Configuration
      # at startup using APP_ENV as the label selector.
      env {
        name  = "APP_ENV"
        value = var.environment
      }
      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }
      env {
        name  = "AZURE_APP_CONFIGURATION_ENDPOINT"
        value = var.azure_app_configuration_endpoint
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.migration_identity_client_id
      }
      # Per-component identity override — migration uses its own managed identity
      # principal as the PostgreSQL user; this overrides any App Config value.
      env {
        name  = "AZURE_POSTGRES_USER"
        value = var.azure_postgres_user_migration
      }
    }
  }

  registry {
    server   = var.container_registry_server
    identity = var.migration_identity_id
  }
}
