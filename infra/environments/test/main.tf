###############################################################################
# test — root module
###############################################################################

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  backend "azurerm" {}
}

provider "azurerm" {
  subscription_id = var.subscription_id
  features {}
}

module "tags" {
  source = "../../modules/tags"

  environment     = var.environment
  project         = var.project
  owner           = var.owner
  additional_tags = var.additional_tags
}

module "resource_group" {
  source = "../../modules/resource-group"

  name     = "rg-${var.project_short}-${var.environment}-${var.location_short}"
  location = var.location
  tags     = module.tags.tags
}
