variable "resource_group_name" {
  description = "Name of the resource group in which to create monitoring resources."
  type        = string
}

variable "location" {
  description = "Azure region for all monitoring resources."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, test, prod). Used in resource names."
  type        = string
}

variable "log_analytics_retention_days" {
  description = "Number of days to retain logs in Log Analytics workspace."
  type        = number
  default     = 30
}

variable "app_insights_sampling_percentage" {
  description = "Sampling percentage for Application Insights telemetry (0-100)."
  type        = number
  default     = 100
}

variable "tags" {
  description = "Tags to apply to all monitoring resources."
  type        = map(string)
  default     = {}
}
