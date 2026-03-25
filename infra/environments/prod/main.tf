terraform {
  required_version = ">= 1.7"
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

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
  subscription_id = var.subscription_id
}

data "azurerm_client_config" "current" {}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "this" {
  name     = "rg-${var.environment}-marketing"
  location = var.location
  tags     = local.tags
}

locals {
  tags = merge(
    {
      environment = var.environment
      project     = "marketing-campaign-builder"
      managed_by  = "terraform"
    },
    var.extra_tags
  )
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

module "networking" {
  source = "../../modules/networking"

  resource_group_name                     = azurerm_resource_group.this.name
  location                                = var.location
  environment                             = var.environment
  vnet_address_space                      = var.vnet_address_space
  container_apps_subnet_address_prefix    = var.container_apps_subnet_address_prefix
  postgresql_subnet_address_prefix        = var.postgresql_subnet_address_prefix
  private_endpoints_subnet_address_prefix = var.private_endpoints_subnet_address_prefix
  enable_private_networking               = var.enable_private_networking
  tags                                    = local.tags
}

# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------

module "monitoring" {
  source = "../../modules/monitoring"

  resource_group_name              = azurerm_resource_group.this.name
  location                         = var.location
  environment                      = var.environment
  log_analytics_retention_days     = var.log_analytics_retention_days
  app_insights_sampling_percentage = var.app_insights_sampling_percentage
  tags                             = local.tags
}

# ---------------------------------------------------------------------------
# Container Registry
# ---------------------------------------------------------------------------

module "container_registry" {
  source = "../../modules/container_registry"

  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  environment                = var.environment
  acr_sku                    = var.acr_sku
  enable_private_networking  = var.enable_private_networking
  private_endpoint_subnet_id = var.enable_private_networking ? module.networking.private_endpoints_subnet_id : null
  private_dns_zone_id        = var.enable_private_networking ? module.networking.acr_private_dns_zone_id : null
  tags                       = local.tags
}

# ---------------------------------------------------------------------------
# Managed Identities + RBAC
# (created before container apps and other resources that reference identity IDs)
# ---------------------------------------------------------------------------

module "identities" {
  source = "../../modules/identities"

  resource_group_name      = azurerm_resource_group.this.name
  location                 = var.location
  environment              = var.environment
  acr_id                   = module.container_registry.acr_id
  service_bus_namespace_id = module.service_bus.service_bus_namespace_id
  key_vault_id             = module.key_vault.key_vault_id
  tags                     = local.tags
}

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------

module "app_configuration" {
  source = "../../modules/app_configuration"

  resource_group_name             = azurerm_resource_group.this.name
  location                        = var.location
  environment                     = var.environment
  sku                             = var.app_configuration_sku
  soft_delete_retention_days      = var.app_configuration_soft_delete_retention_days
  enable_private_networking       = var.enable_private_networking
  private_endpoint_subnet_id      = var.enable_private_networking ? module.networking.private_endpoints_subnet_id : null
  private_dns_zone_id             = var.enable_private_networking ? module.networking.app_configuration_private_dns_zone_id : null
  api_identity_principal_id       = module.identities.api_identity_principal_id
  worker_identity_principal_id    = module.identities.worker_identity_principal_id
  migration_identity_principal_id = module.identities.migration_identity_principal_id
  log_analytics_workspace_id      = module.monitoring.log_analytics_workspace_id
  tags                            = local.tags
}

# ---------------------------------------------------------------------------
# Key Vault
# ---------------------------------------------------------------------------

module "key_vault" {
  source = "../../modules/key_vault"

  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  environment                = var.environment
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days = var.key_vault_soft_delete_retention_days
  purge_protection_enabled   = var.key_vault_purge_protection_enabled
  enable_private_networking  = var.enable_private_networking
  private_endpoint_subnet_id = var.enable_private_networking ? module.networking.private_endpoints_subnet_id : null
  private_dns_zone_id        = var.enable_private_networking ? module.networking.key_vault_private_dns_zone_id : null
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
  tags                       = local.tags
}

# ---------------------------------------------------------------------------
# Service Bus
# ---------------------------------------------------------------------------

module "service_bus" {
  source = "../../modules/service_bus"

  resource_group_name                         = azurerm_resource_group.this.name
  location                                    = var.location
  environment                                 = var.environment
  sku                                         = var.service_bus_sku
  queue_name                                  = var.service_bus_queue_name
  queue_lock_duration                         = var.service_bus_queue_lock_duration
  queue_message_ttl                           = var.service_bus_queue_message_ttl
  queue_max_delivery_count                    = var.service_bus_queue_max_delivery_count
  queue_max_size_mb                           = var.service_bus_queue_max_size_mb
  enable_dead_lettering_on_message_expiration = var.service_bus_enable_dead_lettering
  enable_private_networking                   = var.enable_private_networking
  private_endpoint_subnet_id                  = var.enable_private_networking ? module.networking.private_endpoints_subnet_id : null
  private_dns_zone_id                         = var.enable_private_networking ? module.networking.service_bus_private_dns_zone_id : null
  log_analytics_workspace_id                  = module.monitoring.log_analytics_workspace_id
  tags                                        = local.tags
}

# ---------------------------------------------------------------------------
# PostgreSQL Flexible Server
# ---------------------------------------------------------------------------

module "postgresql" {
  source = "../../modules/postgresql"

  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  environment                = var.environment
  postgresql_version         = var.postgresql_version
  sku_name                   = var.postgresql_sku_name
  storage_mb                 = var.postgresql_storage_mb
  ha_mode                    = var.postgresql_ha_mode
  backup_retention_days      = var.postgresql_backup_retention_days
  geo_redundant_backup       = var.postgresql_geo_redundant_backup
  password_auth_enabled      = var.postgresql_password_auth_enabled
  entra_admin_object_id      = var.entra_admin_object_id
  entra_admin_principal_name = var.entra_admin_principal_name
  administrator_login        = var.postgresql_administrator_login
  administrator_password     = var.postgresql_administrator_password
  enable_private_networking  = var.enable_private_networking
  delegated_subnet_id        = var.enable_private_networking ? module.networking.postgresql_subnet_id : null
  private_dns_zone_id        = var.enable_private_networking ? module.networking.postgresql_private_dns_zone_id : null
  database_name              = var.postgresql_database_name
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
  tags                       = local.tags
}

# ---------------------------------------------------------------------------
# Container Apps
# ---------------------------------------------------------------------------

module "container_apps" {
  source = "../../modules/container_apps"

  resource_group_name            = azurerm_resource_group.this.name
  location                       = var.location
  environment                    = var.environment
  log_analytics_workspace_id     = module.monitoring.log_analytics_workspace_id
  infrastructure_subnet_id       = module.networking.container_apps_subnet_id
  internal_load_balancer_enabled = var.enable_private_networking
  workload_profile_type          = var.container_apps_workload_profile_type
  workload_profile_min_count     = var.container_apps_workload_profile_min_count
  workload_profile_max_count     = var.container_apps_workload_profile_max_count
  container_registry_server      = module.container_registry.acr_login_server

  # API
  api_identity_id        = module.identities.api_identity_id
  api_identity_client_id = module.identities.api_identity_client_id
  api_image              = "${module.container_registry.acr_login_server}/marketing-api:${var.image_tag}"
  api_cpu                = var.api_cpu
  api_memory             = var.api_memory
  api_min_replicas       = var.api_min_replicas
  api_max_replicas       = var.api_max_replicas

  # Worker
  worker_identity_id        = module.identities.worker_identity_id
  worker_identity_client_id = module.identities.worker_identity_client_id
  worker_image              = "${module.container_registry.acr_login_server}/marketing-worker:${var.image_tag}"
  worker_cpu                = var.worker_cpu
  worker_memory             = var.worker_memory
  worker_min_replicas       = var.worker_min_replicas
  worker_max_replicas       = var.worker_max_replicas

  # Frontend
  frontend_image        = "${module.container_registry.acr_login_server}/marketing-frontend:${var.image_tag}"
  frontend_cpu          = var.frontend_cpu
  frontend_memory       = var.frontend_memory
  frontend_min_replicas = var.frontend_min_replicas
  frontend_max_replicas = var.frontend_max_replicas

  # Migration job
  migration_identity_id        = module.identities.migration_identity_id
  migration_identity_client_id = module.identities.migration_identity_client_id
  migration_image              = "${module.container_registry.acr_login_server}/marketing-api:${var.image_tag}"
  migration_cpu                = var.migration_cpu
  migration_memory             = var.migration_memory

  # Shared application config
  azure_postgres_user_api       = module.identities.api_identity_principal_id
  azure_postgres_user_worker    = module.identities.worker_identity_principal_id
  azure_postgres_user_migration = module.identities.migration_identity_principal_id

  # Bootstrap configuration — all other runtime settings are loaded from
  # Azure App Configuration at startup using APP_ENV as the label.
  azure_app_configuration_endpoint = module.app_configuration.app_configuration_endpoint

  tags = local.tags
}
