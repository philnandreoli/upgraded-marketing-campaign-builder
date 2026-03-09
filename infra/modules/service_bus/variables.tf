variable "resource_group_name" {
  description = "Name of the resource group in which to create the Service Bus namespace."
  type        = string
}

variable "location" {
  description = "Azure region for the Service Bus namespace."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names."
  type        = string
}

variable "sku" {
  description = "SKU for the Service Bus namespace. One of: Basic, Standard, Premium."
  type        = string
  default     = "Standard"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.sku)
    error_message = "sku must be one of: Basic, Standard, Premium."
  }
}

variable "queue_name" {
  description = "Name of the workflow jobs queue."
  type        = string
  default     = "workflow-jobs"
}

variable "queue_lock_duration" {
  description = "ISO 8601 duration for message lock. Default PT5M (5 minutes)."
  type        = string
  default     = "PT5M"
}

variable "queue_message_ttl" {
  description = "ISO 8601 duration for message time-to-live. Default P14D (14 days)."
  type        = string
  default     = "P14D"
}

variable "queue_max_delivery_count" {
  description = "Maximum number of deliveries before a message moves to dead-letter queue."
  type        = number
  default     = 10
}

variable "queue_max_size_mb" {
  description = "Maximum queue size in MB."
  type        = number
  default     = 1024
}

variable "enable_dead_lettering_on_message_expiration" {
  description = "Whether to dead-letter messages when they expire."
  type        = bool
  default     = true
}

variable "enable_private_networking" {
  description = "When true and sku is Premium, creates a private endpoint for the Service Bus namespace."
  type        = bool
  default     = false
}

variable "private_endpoint_subnet_id" {
  description = "Subnet ID for the Service Bus private endpoint. Required when enable_private_networking is true."
  type        = string
  default     = null
}

variable "private_dns_zone_id" {
  description = "ID of the private DNS zone for servicebus.windows.net. Required when enable_private_networking is true."
  type        = string
  default     = null
}

variable "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace for diagnostic settings."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to all Service Bus resources."
  type        = map(string)
  default     = {}
}
