variable "resource_group_name" {
  description = "Name of the resource group in which to create the managed identities."
  type        = string
}

variable "location" {
  description = "Azure region for managed identity resources."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names."
  type        = string
}

variable "acr_id" {
  description = "Resource ID of the Azure Container Registry."
  type        = string
}

variable "service_bus_namespace_id" {
  description = "Resource ID of the Service Bus namespace."
  type        = string
}

variable "key_vault_id" {
  description = "Resource ID of the Key Vault."
  type        = string
}

variable "tags" {
  description = "Tags to apply to managed identity resources."
  type        = map(string)
  default     = {}
}
