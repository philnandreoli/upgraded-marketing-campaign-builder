variable "name" {
  description = "Name of the resource group."
  type        = string
}

variable "location" {
  description = "Azure region where the resource group will be created."
  type        = string
}

variable "tags" {
  description = "Tag map to apply to the resource group."
  type        = map(string)
  default     = {}
}
