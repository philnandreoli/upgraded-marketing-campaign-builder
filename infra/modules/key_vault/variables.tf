variable "resource_group_name" {
  description = "Name of the resource group in which to create the Key Vault."
  type        = string
}

variable "location" {
  description = "Azure region for the Key Vault."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names."
  type        = string
}

variable "tenant_id" {
  description = "Azure tenant ID. Used for Key Vault configuration."
  type        = string
}

variable "soft_delete_retention_days" {
  description = "Number of days to retain deleted keys/secrets/certificates (7-90)."
  type        = number
  default     = 7

  validation {
    condition     = var.soft_delete_retention_days >= 7 && var.soft_delete_retention_days <= 90
    error_message = "soft_delete_retention_days must be between 7 and 90."
  }
}

variable "purge_protection_enabled" {
  description = "Whether purge protection is enabled. Should be true for prod."
  type        = bool
  default     = false
}

variable "enable_private_networking" {
  description = "When true, creates a private endpoint for the Key Vault."
  type        = bool
  default     = false
}

variable "private_endpoint_subnet_id" {
  description = "Subnet ID for the Key Vault private endpoint. Required when enable_private_networking is true."
  type        = string
  default     = null
}

variable "private_dns_zone_id" {
  description = "ID of the private DNS zone for vaultcore.azure.net. Required when enable_private_networking is true."
  type        = string
  default     = null
}

variable "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace for diagnostic settings."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to the Key Vault."
  type        = map(string)
  default     = {}
}
