variable "resource_group_name" {
  description = "Name of the resource group in which to create the container registry."
  type        = string
}

variable "location" {
  description = "Azure region for the container registry."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names."
  type        = string
}

variable "acr_sku" {
  description = "SKU for the Azure Container Registry. One of: Basic, Standard, Premium."
  type        = string
  default     = "Basic"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "acr_sku must be one of: Basic, Standard, Premium."
  }
}

variable "enable_private_networking" {
  description = "When true and acr_sku is Premium, creates a private endpoint for the registry."
  type        = bool
  default     = false
}

variable "private_endpoint_subnet_id" {
  description = "Subnet ID for the ACR private endpoint. Required when enable_private_networking is true."
  type        = string
  default     = null
}

variable "private_dns_zone_id" {
  description = "ID of the private DNS zone for azurecr.io. Required when enable_private_networking is true."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to the container registry."
  type        = map(string)
  default     = {}
}
