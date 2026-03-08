###############################################################################
# dev — root module
#
# Deploys all Marketing Campaign Builder infrastructure into the dev
# environment using the shared reusable modules under ../../modules/.
#
# Run order:
#   terraform -chdir=infra/environments/dev init
#   terraform -chdir=infra/environments/dev plan
#   terraform -chdir=infra/environments/dev apply
###############################################################################

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Remote state is configured in backend.hcl (partial backend config).
  # Run: terraform init -backend-config=backend.hcl
  backend "azurerm" {}
}

provider "azurerm" {
  subscription_id = var.subscription_id
  features {}
}

# ---------------------------------------------------------------------------
# Standard tags
# ---------------------------------------------------------------------------
module "tags" {
  source = "../../modules/tags"

  environment     = var.environment
  project         = var.project
  owner           = var.owner
  additional_tags = var.additional_tags
}

# ---------------------------------------------------------------------------
# Resource group
# ---------------------------------------------------------------------------
module "resource_group" {
  source = "../../modules/resource-group"

  name     = "rg-${var.project_short}-${var.environment}-${var.location_short}"
  location = var.location
  tags     = module.tags.tags
}
