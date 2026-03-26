variable "resource_group_name" {
  description = "Name of the resource group in which to create the App Configuration store."
  type        = string
}

variable "location" {
  description = "Azure region for the App Configuration store."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names and as the default label."
  type        = string
}

variable "sku" {
  description = "SKU for the App Configuration store. 'standard' is required for Key Vault reference support and is strongly recommended for all environments. 'free' does not support Key Vault references or private endpoints."
  type        = string
  default     = "standard"
}

variable "soft_delete_retention_days" {
  description = "Number of days to retain soft-deleted configuration items."
  type        = number
  default     = 7
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

variable "enable_private_networking" {
  description = "When true, disables public network access and creates a private endpoint."
  type        = bool
  default     = false
}

variable "private_endpoint_subnet_id" {
  description = "Subnet ID for the private endpoint. Required when enable_private_networking = true."
  type        = string
  default     = null
}

variable "private_dns_zone_id" {
  description = "Resource ID of the private DNS zone for App Configuration (privatelink.azconfig.io). Required when enable_private_networking = true."
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Identity principal IDs (for RBAC)
# ---------------------------------------------------------------------------

variable "api_identity_principal_id" {
  description = "Principal ID of the API managed identity. Granted App Configuration Data Reader."
  type        = string
}

variable "worker_identity_principal_id" {
  description = "Principal ID of the Worker managed identity. Granted App Configuration Data Reader."
  type        = string
}

variable "migration_identity_principal_id" {
  description = "Principal ID of the Migration managed identity. Granted App Configuration Data Reader."
  type        = string
}

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

variable "log_analytics_workspace_id" {
  description = "Resource ID of the Log Analytics workspace for diagnostic logs. Optional."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to App Configuration resources."
  type        = map(string)
  default     = {}
}
