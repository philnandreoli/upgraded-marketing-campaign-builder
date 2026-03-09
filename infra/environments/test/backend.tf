# Test environment remote state configuration.

terraform {
  backend "azurerm" {
    resource_group_name  = "rg-marketing-tfstate"
    storage_account_name = "stmktgtfstate"
    container_name       = "tfstate-test"
    key                  = "marketing-campaign.tfstate"
  }
}
