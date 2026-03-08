###############################################################################
# test — variable declarations
###############################################################################

variable "subscription_id" {
  description = "Azure subscription ID where test resources are deployed."
  type        = string
  sensitive   = true
}

variable "tenant_id" {
  description = "Azure AD tenant ID."
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment label applied to all resources and tags."
  type        = string
  default     = "test"
}

variable "location" {
  description = "Primary Azure region for all resources."
  type        = string
  default     = "eastus2"
}

variable "location_short" {
  description = "Short location code used in resource names."
  type        = string
  default     = "eus2"
}

variable "project" {
  description = "Full project name used in tags."
  type        = string
  default     = "marketing-campaign-builder"
}

variable "project_short" {
  description = "Short project identifier used in resource names (3-8 chars)."
  type        = string
  default     = "mcb"
}

variable "owner" {
  description = "Team or individual responsible for the test environment."
  type        = string
  default     = ""
}

variable "additional_tags" {
  description = "Extra tags to merge on top of the standard set."
  type        = map(string)
  default     = {}
}
