resource_group_name  = "rg-mcb-tfstate"
storage_account_name = "mcbtfstate" # set to actual name from bootstrap-state.sh
container_name       = "tfstate"
key                  = "environments/test/terraform.tfstate"
use_azuread_auth     = true
