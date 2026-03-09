variable "resource_group_name" {
  description = "Name of the resource group in which to create networking resources."
  type        = string
}

variable "location" {
  description = "Azure region for all networking resources."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names."
  type        = string
}

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
  description = "When true, creates private DNS zones and links them to the VNet. Set to true for prod."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to all networking resources."
  type        = map(string)
  default     = {}
}
