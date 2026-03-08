#!/usr/bin/env bash
# bootstrap-state.sh
#
# Creates the Azure Storage account and blob container used to store Terraform
# remote state for all environments (dev, test, prod).
#
# This script is run ONCE by an operator with Owner/Contributor rights on the
# target subscription BEFORE running `terraform init` for any environment.
#
# Prerequisites:
#   - Azure CLI (az) installed and logged in: az login
#   - Sufficient RBAC permissions on the target subscription
#
# Usage:
#   ./infra/scripts/bootstrap-state.sh \
#     --subscription  <subscription-id>  \
#     --location      eastus2            \
#     [--resource-group rg-mcb-tfstate]  \
#     [--account-name   mcbtfstate]
#
# The storage account name must be globally unique (3-24 lowercase alphanumeric).
# If the desired name is taken, append a short random suffix:
#   --account-name mcbtfstate$(openssl rand -hex 3)
# -----------------------------------------------------------------------------

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
SUBSCRIPTION_ID=""
LOCATION="eastus2"
RESOURCE_GROUP="rg-mcb-tfstate"
ACCOUNT_NAME="mcbtfstate"
CONTAINER_NAME="tfstate"

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --subscription)  SUBSCRIPTION_ID="$2"; shift 2 ;;
    --location)      LOCATION="$2";        shift 2 ;;
    --resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    --account-name)  ACCOUNT_NAME="$2";    shift 2 ;;
    --container)     CONTAINER_NAME="$2";  shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

if [[ -z "$SUBSCRIPTION_ID" ]]; then
  echo "Error: --subscription is required."
  exit 1
fi

# ── Set active subscription ───────────────────────────────────────────────────
echo "Setting active subscription: $SUBSCRIPTION_ID"
az account set --subscription "$SUBSCRIPTION_ID"

# ── Resource group ────────────────────────────────────────────────────────────
echo "Creating resource group: $RESOURCE_GROUP ($LOCATION)"
az group create \
  --name     "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags     "project=marketing-campaign-builder" "managed_by=terraform" "component=tfstate" \
  --output   none

# ── Storage account ───────────────────────────────────────────────────────────
echo "Creating storage account: $ACCOUNT_NAME"
az storage account create \
  --name                   "$ACCOUNT_NAME" \
  --resource-group         "$RESOURCE_GROUP" \
  --location               "$LOCATION" \
  --sku                    Standard_LRS \
  --kind                   StorageV2 \
  --allow-blob-public-access false \
  --min-tls-version        TLS1_2 \
  --tags "project=marketing-campaign-builder" "managed_by=terraform" "component=tfstate" \
  --output none

# Enable versioning so accidental state deletions are recoverable.
az storage account blob-service-properties update \
  --account-name        "$ACCOUNT_NAME" \
  --resource-group      "$RESOURCE_GROUP" \
  --enable-versioning   true \
  --output none

# ── Blob container ────────────────────────────────────────────────────────────
echo "Creating blob container: $CONTAINER_NAME"
az storage container create \
  --name              "$CONTAINER_NAME" \
  --account-name      "$ACCOUNT_NAME" \
  --auth-mode         login \
  --output none

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Bootstrap complete. Update the backend.hcl files in each environment with:"
echo "  resource_group_name  = \"$RESOURCE_GROUP\""
echo "  storage_account_name = \"$ACCOUNT_NAME\""
echo "  container_name       = \"$CONTAINER_NAME\""
echo ""
echo "Then initialize each environment:"
echo "  terraform -chdir=infra/environments/dev  init -backend-config=backend.hcl"
echo "  terraform -chdir=infra/environments/test init -backend-config=backend.hcl"
echo "  terraform -chdir=infra/environments/prod init -backend-config=backend.hcl"
