variable "resource_group_name" {
  description = "Name of the resource group in which to create the PostgreSQL server."
  type        = string
}

variable "location" {
  description = "Azure region for the PostgreSQL server."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names."
  type        = string
}

variable "postgresql_version" {
  description = "Major version of PostgreSQL."
  type        = string
  default     = "16"
}

variable "sku_name" {
  description = "SKU for the PostgreSQL Flexible Server (e.g. Standard_B1ms, Standard_D4s_v3)."
  type        = string
  default     = "Standard_B1ms"
}

variable "storage_mb" {
  description = "Storage capacity in MB for the PostgreSQL Flexible Server."
  type        = number
  default     = 32768
}

variable "ha_mode" {
  description = "High availability mode. One of: Disabled, SameZone, ZoneRedundant."
  type        = string
  default     = "Disabled"

  validation {
    condition     = contains(["Disabled", "SameZone", "ZoneRedundant"], var.ha_mode)
    error_message = "ha_mode must be one of: Disabled, SameZone, ZoneRedundant."
  }
}

variable "backup_retention_days" {
  description = "Number of days to retain backups (7-35)."
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 7 and 35."
  }
}

variable "geo_redundant_backup" {
  description = "Whether geo-redundant backups are enabled."
  type        = bool
  default     = false
}

variable "password_auth_enabled" {
  description = "When true, local password authentication is enabled alongside Entra auth. Set to false for prod."
  type        = bool
  default     = true
}

variable "entra_admin_object_id" {
  description = "Object ID of the Entra ID user or group to set as PostgreSQL Entra admin."
  type        = string
}

variable "entra_admin_principal_name" {
  description = "User principal name or display name of the Entra admin."
  type        = string
}

variable "administrator_login" {
  description = "Local administrator login name. Only used when password_auth_enabled is true."
  type        = string
  default     = "pgadmin"
}

variable "administrator_password" {
  description = "Local administrator password. Only used when password_auth_enabled is true. Use a secret store in production."
  type        = string
  sensitive   = true
  default     = null
}

variable "enable_private_networking" {
  description = "When true, uses VNet integration (private access). When false, uses public access with firewall rules."
  type        = bool
  default     = false
}

variable "delegated_subnet_id" {
  description = "Subnet ID delegated to Microsoft.DBforPostgreSQL/flexibleServers. Required when enable_private_networking is true."
  type        = string
  default     = null
}

variable "private_dns_zone_id" {
  description = "ID of the private DNS zone for postgres.database.azure.com. Required when enable_private_networking is true."
  type        = string
  default     = null
}

variable "database_name" {
  description = "Name of the application database to create."
  type        = string
  default     = "campaigns"
}

variable "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace for diagnostic settings."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to all PostgreSQL resources."
  type        = map(string)
  default     = {}
}
