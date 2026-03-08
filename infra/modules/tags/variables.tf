variable "environment" {
  description = "Deployment environment name (dev, test, prod)."
  type        = string

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be one of: dev, test, prod."
  }
}

variable "project" {
  description = "Project name used in tagging and resource naming."
  type        = string
  default     = "marketing-campaign-builder"
}

variable "owner" {
  description = "Team or individual responsible for these resources."
  type        = string
  default     = ""
}

variable "component" {
  description = "Logical component or service name (e.g. api, worker, database)."
  type        = string
  default     = ""
}

variable "additional_tags" {
  description = "Extra key/value tags to merge into the standard tag set."
  type        = map(string)
  default     = {}
}
