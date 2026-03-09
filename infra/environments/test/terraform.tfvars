# ---------------------------------------------------------------------------
# Test environment variable values
# ---------------------------------------------------------------------------

# Required — fill in before applying
subscription_id            = ""
entra_admin_object_id      = ""
entra_admin_principal_name = ""

# Location
location    = "eastus"
environment = "test"

# Networking — public access for test
enable_private_networking               = false
vnet_address_space                      = ["10.1.0.0/16"]
container_apps_subnet_address_prefix    = "10.1.0.0/23"
postgresql_subnet_address_prefix        = "10.1.2.0/27"
private_endpoints_subnet_address_prefix = "10.1.2.32/27"

# Monitoring
log_analytics_retention_days     = 30
app_insights_sampling_percentage = 100

# Container Registry — Standard for test
acr_sku = "Standard"

# Key Vault
key_vault_soft_delete_retention_days = 7
key_vault_purge_protection_enabled   = false

# Service Bus — Standard for test
service_bus_sku                      = "Standard"
service_bus_queue_name               = "workflow-jobs"
service_bus_queue_lock_duration      = "PT5M"
service_bus_queue_message_ttl        = "P14D"
service_bus_queue_max_delivery_count = 10
service_bus_queue_max_size_mb        = 1024
service_bus_enable_dead_lettering    = true

# PostgreSQL — slightly larger SKU for test, password auth enabled
postgresql_version               = "16"
postgresql_sku_name              = "Standard_B2ms"
postgresql_storage_mb            = 32768
postgresql_ha_mode               = "Disabled"
postgresql_backup_retention_days = 7
postgresql_geo_redundant_backup  = false
postgresql_password_auth_enabled = true
postgresql_administrator_login   = "pgadmin"
postgresql_database_name         = "campaigns"

# Container Apps — Consumption profile
container_apps_workload_profile_type      = "Consumption"
container_apps_workload_profile_min_count = 0
container_apps_workload_profile_max_count = 0

image_tag = "latest"

api_cpu          = 0.5
api_memory       = "1Gi"
api_min_replicas = 1
api_max_replicas = 3

worker_cpu          = 0.5
worker_memory       = "1Gi"
worker_min_replicas = 1
worker_max_replicas = 3

frontend_cpu          = 0.5
frontend_memory       = "1Gi"
frontend_min_replicas = 1
frontend_max_replicas = 3

migration_cpu    = 0.5
migration_memory = "1Gi"

# Azure AI
azure_ai_project_endpoint      = ""
azure_ai_model_deployment_name = "gpt-4"
