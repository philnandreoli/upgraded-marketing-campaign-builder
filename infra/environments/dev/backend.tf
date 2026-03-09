# Dev environment remote state configuration.
# Update resource_group_name, storage_account_name with your actual values
# before running terraform init.

terraform {
  backend "azurerm" {
    resource_group_name  = "rg-marketing-tfstate"
    storage_account_name = "stmktgtfstate"
    container_name       = "tfstate-dev"
    key                  = "marketing-campaign.tfstate"
  }
}
