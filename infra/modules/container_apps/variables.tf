variable "resource_group_name" {
  description = "Name of the resource group in which to create Container Apps resources."
  type        = string
}

variable "location" {
  description = "Azure region for Container Apps resources."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names."
  type        = string
}

variable "log_analytics_workspace_id" {
  description = "Resource ID of the Log Analytics workspace for Container Apps Environment."
  type        = string
}

variable "infrastructure_subnet_id" {
  description = "Subnet ID for the Container Apps Environment infrastructure. Required for VNet integration."
  type        = string
  default     = null
}

variable "internal_load_balancer_enabled" {
  description = "When true, the Container Apps Environment uses an internal load balancer (no public ingress). Set to true for prod private networking."
  type        = bool
  default     = false
}

variable "workload_profile_type" {
  description = "Workload profile type for the Container Apps Environment. Use Consumption for dev/test, D4 for prod."
  type        = string
  default     = "Consumption"
}

variable "workload_profile_min_count" {
  description = "Minimum node count for the dedicated workload profile. Only applicable for non-Consumption profiles."
  type        = number
  default     = 1
}

variable "workload_profile_max_count" {
  description = "Maximum node count for the dedicated workload profile. Only applicable for non-Consumption profiles."
  type        = number
  default     = 3
}

# --- Container image ---

variable "container_registry_server" {
  description = "Login server URL for the Azure Container Registry (e.g. myacr.azurecr.io)."
  type        = string
}

# --- API Container App ---

variable "api_identity_id" {
  description = "Resource ID of the user-assigned managed identity for the API Container App."
  type        = string
}

variable "api_identity_client_id" {
  description = "Client ID of the user-assigned managed identity for the API Container App."
  type        = string
}

variable "api_image" {
  description = "Container image for the API app (e.g. myacr.azurecr.io/marketing-api:latest)."
  type        = string
}

variable "api_cpu" {
  description = "CPU allocation for the API container (e.g. 0.5)."
  type        = number
  default     = 0.5
}

variable "api_memory" {
  description = "Memory allocation for the API container (e.g. 1Gi)."
  type        = string
  default     = "1Gi"
}

variable "api_min_replicas" {
  description = "Minimum replica count for the API Container App."
  type        = number
  default     = 1
}

variable "api_max_replicas" {
  description = "Maximum replica count for the API Container App."
  type        = number
  default     = 3
}

# --- Worker Container App ---

variable "worker_identity_id" {
  description = "Resource ID of the user-assigned managed identity for the Worker Container App."
  type        = string
}

variable "worker_identity_client_id" {
  description = "Client ID of the user-assigned managed identity for the Worker Container App."
  type        = string
}

variable "worker_image" {
  description = "Container image for the Worker app (e.g. myacr.azurecr.io/marketing-worker:latest)."
  type        = string
}

variable "worker_cpu" {
  description = "CPU allocation for the Worker container (e.g. 0.5)."
  type        = number
  default     = 0.5
}

variable "worker_memory" {
  description = "Memory allocation for the Worker container (e.g. 1Gi)."
  type        = string
  default     = "1Gi"
}

variable "worker_min_replicas" {
  description = "Minimum replica count for the Worker Container App."
  type        = number
  default     = 1
}

variable "worker_max_replicas" {
  description = "Maximum replica count for the Worker Container App."
  type        = number
  default     = 3
}

# --- Frontend Container App ---

variable "frontend_image" {
  description = "Container image for the Frontend app (e.g. myacr.azurecr.io/marketing-frontend:latest)."
  type        = string
}

variable "frontend_cpu" {
  description = "CPU allocation for the Frontend container."
  type        = number
  default     = 0.5
}

variable "frontend_memory" {
  description = "Memory allocation for the Frontend container."
  type        = string
  default     = "1Gi"
}

variable "frontend_min_replicas" {
  description = "Minimum replica count for the Frontend Container App."
  type        = number
  default     = 1
}

variable "frontend_max_replicas" {
  description = "Maximum replica count for the Frontend Container App."
  type        = number
  default     = 3
}

# --- Migration Container Apps Job ---

variable "migration_identity_id" {
  description = "Resource ID of the user-assigned managed identity for the migration job."
  type        = string
}

variable "migration_identity_client_id" {
  description = "Client ID of the user-assigned managed identity for the migration job."
  type        = string
}

variable "migration_image" {
  description = "Container image for the migration job."
  type        = string
}

variable "migration_cpu" {
  description = "CPU allocation for the migration job container."
  type        = number
  default     = 0.5
}

variable "migration_memory" {
  description = "Memory allocation for the migration job container."
  type        = string
  default     = "1Gi"
}

# --- Shared application configuration ---

variable "postgresql_fqdn" {
  description = "FQDN of the PostgreSQL Flexible Server."
  type        = string
}

variable "postgresql_database_name" {
  description = "Name of the PostgreSQL database."
  type        = string
}

variable "azure_postgres_user_api" {
  description = "PostgreSQL username for the API managed identity."
  type        = string
}

variable "azure_postgres_user_worker" {
  description = "PostgreSQL username for the Worker managed identity."
  type        = string
}

variable "azure_postgres_user_migration" {
  description = "PostgreSQL username for the migration managed identity."
  type        = string
}

variable "service_bus_namespace_fqdn" {
  description = "FQDN of the Service Bus namespace."
  type        = string
}

variable "service_bus_queue_name" {
  description = "Name of the Service Bus workflow queue."
  type        = string
}

variable "key_vault_uri" {
  description = "URI of the Key Vault."
  type        = string
}

variable "application_insights_connection_string" {
  description = "Application Insights connection string."
  type        = string
}

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

variable "tags" {
  description = "Tags to apply to all Container Apps resources."
  type        = map(string)
  default     = {}
}
