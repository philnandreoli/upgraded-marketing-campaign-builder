variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Environment name. Should be 'dev' for this root module."
  type        = string
  default     = "dev"
}

variable "extra_tags" {
  description = "Additional tags to merge with the default tag set."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

variable "vnet_address_space" {
  description = "Address space for the virtual network."
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "container_apps_subnet_address_prefix" {
  description = "Address prefix for the Container Apps delegated subnet."
  type        = string
  default     = "10.0.0.0/23"
}

variable "postgresql_subnet_address_prefix" {
  description = "Address prefix for the PostgreSQL delegated subnet."
  type        = string
  default     = "10.0.2.0/27"
}

variable "private_endpoints_subnet_address_prefix" {
  description = "Address prefix for the private endpoints subnet."
  type        = string
  default     = "10.0.2.32/27"
}

variable "enable_private_networking" {
  description = "Enable private networking (private DNS zones, private endpoints)."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------

variable "log_analytics_retention_days" {
  description = "Log Analytics workspace retention in days."
  type        = number
  default     = 30
}

variable "app_insights_sampling_percentage" {
  description = "Application Insights sampling percentage."
  type        = number
  default     = 100
}

# ---------------------------------------------------------------------------
# Container Registry
# ---------------------------------------------------------------------------

variable "acr_sku" {
  description = "SKU for the Azure Container Registry."
  type        = string
  default     = "Basic"
}

# ---------------------------------------------------------------------------
# Key Vault
# ---------------------------------------------------------------------------

variable "key_vault_soft_delete_retention_days" {
  description = "Soft-delete retention days for the Key Vault."
  type        = number
  default     = 7
}

variable "key_vault_purge_protection_enabled" {
  description = "Whether purge protection is enabled on the Key Vault."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Service Bus
# ---------------------------------------------------------------------------

variable "service_bus_sku" {
  description = "SKU for the Service Bus namespace."
  type        = string
  default     = "Standard"
}

variable "service_bus_queue_name" {
  description = "Name of the workflow jobs queue."
  type        = string
  default     = "workflow-jobs"
}

variable "service_bus_queue_lock_duration" {
  description = "ISO 8601 lock duration for Service Bus messages."
  type        = string
  default     = "PT5M"
}

variable "service_bus_queue_message_ttl" {
  description = "ISO 8601 message TTL for the Service Bus queue."
  type        = string
  default     = "P14D"
}

variable "service_bus_queue_max_delivery_count" {
  description = "Maximum delivery count before dead-lettering."
  type        = number
  default     = 10
}

variable "service_bus_queue_max_size_mb" {
  description = "Maximum queue size in MB."
  type        = number
  default     = 1024
}

variable "service_bus_enable_dead_lettering" {
  description = "Dead-letter messages on expiration."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

variable "postgresql_version" {
  description = "PostgreSQL major version."
  type        = string
  default     = "16"
}

variable "postgresql_sku_name" {
  description = "SKU name for the PostgreSQL Flexible Server."
  type        = string
  default     = "Standard_B1ms"
}

variable "postgresql_storage_mb" {
  description = "Storage in MB for the PostgreSQL Flexible Server."
  type        = number
  default     = 32768
}

variable "postgresql_ha_mode" {
  description = "High availability mode for PostgreSQL."
  type        = string
  default     = "Disabled"
}

variable "postgresql_backup_retention_days" {
  description = "Backup retention days for PostgreSQL."
  type        = number
  default     = 7
}

variable "postgresql_geo_redundant_backup" {
  description = "Enable geo-redundant backup for PostgreSQL."
  type        = bool
  default     = false
}

variable "postgresql_password_auth_enabled" {
  description = "Enable local password auth for PostgreSQL."
  type        = bool
  default     = true
}

variable "entra_admin_object_id" {
  description = "Object ID of the Entra ID PostgreSQL admin."
  type        = string
}

variable "entra_admin_principal_name" {
  description = "Principal name of the Entra ID PostgreSQL admin."
  type        = string
}

variable "postgresql_administrator_login" {
  description = "Local PostgreSQL administrator login."
  type        = string
  default     = "pgadmin"
}

variable "postgresql_administrator_password" {
  description = "Local PostgreSQL administrator password. Leave null to auto-generate."
  type        = string
  sensitive   = true
  default     = null
}

variable "postgresql_database_name" {
  description = "Name of the application database."
  type        = string
  default     = "campaigns"
}

# ---------------------------------------------------------------------------
# Container Apps
# ---------------------------------------------------------------------------

variable "container_apps_workload_profile_type" {
  description = "Workload profile type for the Container Apps Environment."
  type        = string
  default     = "Consumption"
}

variable "container_apps_workload_profile_min_count" {
  description = "Minimum node count for dedicated workload profile."
  type        = number
  default     = 1
}

variable "container_apps_workload_profile_max_count" {
  description = "Maximum node count for dedicated workload profile."
  type        = number
  default     = 3
}

variable "image_tag" {
  description = "Container image tag to deploy (e.g. latest, git SHA)."
  type        = string
  default     = "latest"
}

variable "api_cpu" {
  description = "CPU for the API Container App."
  type        = number
  default     = 0.5
}

variable "api_memory" {
  description = "Memory for the API Container App."
  type        = string
  default     = "1Gi"
}

variable "api_min_replicas" {
  description = "Minimum replicas for the API Container App."
  type        = number
  default     = 1
}

variable "api_max_replicas" {
  description = "Maximum replicas for the API Container App."
  type        = number
  default     = 3
}

variable "worker_cpu" {
  description = "CPU for the Worker Container App."
  type        = number
  default     = 0.5
}

variable "worker_memory" {
  description = "Memory for the Worker Container App."
  type        = string
  default     = "1Gi"
}

variable "worker_min_replicas" {
  description = "Minimum replicas for the Worker Container App."
  type        = number
  default     = 1
}

variable "worker_max_replicas" {
  description = "Maximum replicas for the Worker Container App."
  type        = number
  default     = 3
}

variable "frontend_cpu" {
  description = "CPU for the Frontend Container App."
  type        = number
  default     = 0.5
}

variable "frontend_memory" {
  description = "Memory for the Frontend Container App."
  type        = string
  default     = "1Gi"
}

variable "frontend_min_replicas" {
  description = "Minimum replicas for the Frontend Container App."
  type        = number
  default     = 1
}

variable "frontend_max_replicas" {
  description = "Maximum replicas for the Frontend Container App."
  type        = number
  default     = 3
}

variable "migration_cpu" {
  description = "CPU for the migration job container."
  type        = number
  default     = 0.5
}

variable "migration_memory" {
  description = "Memory for the migration job container."
  type        = string
  default     = "1Gi"
}

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------

variable "app_configuration_sku" {
  description = "SKU for the Azure App Configuration store. 'free' for dev; 'standard' recommended for prod."
  type        = string
  default     = "standard"
}

variable "app_configuration_soft_delete_retention_days" {
  description = "Soft-delete retention days for App Configuration key-values."
  type        = number
  default     = 7
}

# ---------------------------------------------------------------------------
# Azure AI
# ---------------------------------------------------------------------------

variable "azure_ai_project_endpoint" {
  description = "Azure AI Foundry project endpoint URL."
  type        = string
  default     = ""
}

variable "azure_ai_model_deployment_name" {
  description = "Azure AI model deployment name."
  type        = string
  default     = "gpt-4"
}
