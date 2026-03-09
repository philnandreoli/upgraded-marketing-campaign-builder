output "service_bus_namespace_id" {
  description = "Resource ID of the Service Bus namespace."
  value       = azurerm_servicebus_namespace.this.id
}

output "service_bus_namespace_name" {
  description = "Name of the Service Bus namespace."
  value       = azurerm_servicebus_namespace.this.name
}

output "service_bus_namespace_fqdn" {
  description = "Fully qualified domain name of the Service Bus namespace."
  value       = "${azurerm_servicebus_namespace.this.name}.servicebus.windows.net"
}

output "service_bus_queue_id" {
  description = "Resource ID of the workflow jobs queue."
  value       = azurerm_servicebus_queue.workflow_jobs.id
}

output "service_bus_queue_name" {
  description = "Name of the workflow jobs queue."
  value       = azurerm_servicebus_queue.workflow_jobs.name
}
