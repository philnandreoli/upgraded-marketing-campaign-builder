output "resource_group_name" {
  description = "Name of the test resource group."
  value       = module.resource_group.name
}

output "resource_group_id" {
  description = "Resource ID of the test resource group."
  value       = module.resource_group.id
}

output "location" {
  description = "Azure region for the test environment."
  value       = module.resource_group.location
}

output "tags" {
  description = "Standard tags applied to test resources."
  value       = module.tags.tags
}
