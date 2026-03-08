# test — non-sensitive variable values
#
# Sensitive values (subscription_id, tenant_id) are NOT stored here.
# Pass them via:
#   export TF_VAR_subscription_id="<test-subscription-id>"
#   export TF_VAR_tenant_id="<tenant-id>"

environment     = "test"
location        = "eastus2"
location_short  = "eus2"
project         = "marketing-campaign-builder"
project_short   = "mcb"
owner           = ""
additional_tags = {}
