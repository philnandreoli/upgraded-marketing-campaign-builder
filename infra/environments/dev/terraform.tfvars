# dev — non-sensitive variable values
#
# Sensitive values (subscription_id, tenant_id) are NOT stored here.
# Pass them via environment variables:
#   export TF_VAR_subscription_id="<dev-subscription-id>"
#   export TF_VAR_tenant_id="<tenant-id>"
# or supply them on the command line:
#   terraform apply -var="subscription_id=..." -var="tenant_id=..."

environment     = "dev"
location        = "eastus2"
location_short  = "eus2"
project         = "marketing-campaign-builder"
project_short   = "mcb"
owner           = ""
additional_tags = {}
