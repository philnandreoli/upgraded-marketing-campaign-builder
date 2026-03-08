# dev backend configuration — passed to `terraform init -backend-config=backend.hcl`
#
# These values are intentionally NOT stored in Terraform state; they are
# supplied at init time so that different engineers or CI runners can use the
# same config file without hard-coding credentials.
#
# The state storage account is created once by infra/scripts/bootstrap-state.sh.
#
# Variable           | Description
# -------------------|----------------------------------------------------------
# resource_group_name| Resource group that holds the state storage account
# storage_account_name| Storage account name (globally unique, see bootstrap script)
# container_name     | Blob container for all environment state files
# key                | Path within the container for this environment's state
# use_oidc           | Use OIDC (Workload Identity Federation) for auth in CI
#
resource_group_name  = "rg-mcb-tfstate"
storage_account_name = "mcbtfstate" # set to actual name from bootstrap-state.sh
container_name       = "tfstate"
key                  = "environments/dev/terraform.tfstate"
use_oidc             = true
