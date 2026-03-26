# ---------------------------------------------------------------------------
# Production environment variable values
# ---------------------------------------------------------------------------
# NOTE: sensitive values (subscription_id, entra_admin_object_id,
# postgresql_administrator_password) should be supplied via environment
# variables (TF_VAR_*) or a secrets manager — do not commit secrets here.
# ---------------------------------------------------------------------------

# Required — fill in before applying
subscription_id            = ""
entra_admin_object_id      = ""
entra_admin_principal_name = ""

# Location
location    = "eastus"
environment = "prod"

# Networking — private access for prod
enable_private_networking               = true
vnet_address_space                      = ["10.2.0.0/16"]
container_apps_subnet_address_prefix    = "10.2.0.0/23"
postgresql_subnet_address_prefix        = "10.2.2.0/27"
private_endpoints_subnet_address_prefix = "10.2.2.32/27"

# Monitoring — longer retention for prod
log_analytics_retention_days     = 90
app_insights_sampling_percentage = 25

# Container Registry — Premium for prod (supports private endpoints)
acr_sku = "Premium"

# Key Vault — purge protection enabled for prod
key_vault_soft_delete_retention_days = 90
key_vault_purge_protection_enabled   = true

# Service Bus — Premium for prod (supports private endpoints)
service_bus_sku                      = "Premium"
service_bus_queue_name               = "workflow-jobs"
service_bus_queue_lock_duration      = "PT5M"
service_bus_queue_message_ttl        = "P14D"
service_bus_queue_max_delivery_count = 10
service_bus_queue_max_size_mb        = 1024
service_bus_enable_dead_lettering    = true

# PostgreSQL — production-grade SKU, HA, no password auth
postgresql_version               = "16"
postgresql_sku_name              = "Standard_D4s_v3"
postgresql_storage_mb            = 131072
postgresql_ha_mode               = "SameZone"
postgresql_backup_retention_days = 35
postgresql_geo_redundant_backup  = false
postgresql_password_auth_enabled = false
postgresql_administrator_login   = "pgadmin"
postgresql_database_name         = "campaigns"

# Container Apps — dedicated D4 profile for prod
container_apps_workload_profile_type      = "D4"
container_apps_workload_profile_min_count = 1
container_apps_workload_profile_max_count = 3

image_tag = "latest"

api_cpu          = 1.0
api_memory       = "2Gi"
api_min_replicas = 2
api_max_replicas = 10

worker_cpu          = 1.0
worker_memory       = "2Gi"
worker_min_replicas = 1
worker_max_replicas = 5

frontend_cpu          = 0.5
frontend_memory       = "1Gi"
frontend_min_replicas = 2
frontend_max_replicas = 10

migration_cpu    = 0.5
migration_memory = "1Gi"

# App Configuration — standard SKU for prod
app_configuration_sku                        = "standard"
app_configuration_soft_delete_retention_days = 7

# Azure AI
azure_ai_project_endpoint      = ""
azure_ai_model_deployment_name = "gpt-4"
