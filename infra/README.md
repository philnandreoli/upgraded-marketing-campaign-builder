# Infrastructure — Marketing Campaign Builder

This directory contains the Terraform configuration that provisions the Azure infrastructure for the **Marketing Campaign Builder** application across three environments: `dev`, `test`, and `prod`.

## Directory Layout

```
infra/
├── README.md                    # This file
├── environments/
│   ├── dev/                     # Dev environment root module
│   │   ├── backend.tf           # Azure Blob remote-state config
│   │   ├── main.tf              # Calls shared modules with dev variables
│   │   ├── variables.tf         # Variable declarations
│   │   ├── terraform.tfvars     # Dev-specific values
│   │   └── outputs.tf           # Outputs consumed by GitHub Actions
│   ├── test/                    # Test environment (same structure)
│   └── prod/                    # Production environment (same structure)
└── modules/
    ├── networking/              # VNet, subnets, NSGs, private DNS zones
    ├── monitoring/              # Log Analytics + Application Insights
    ├── container_registry/      # Azure Container Registry
    ├── postgresql/              # Azure Database for PostgreSQL Flexible Server
    ├── service_bus/             # Azure Service Bus namespace + queue
    ├── key_vault/               # Azure Key Vault (RBAC mode)
    ├── identities/              # Managed identities + RBAC assignments
    └── container_apps/          # Container Apps Environment + apps + migration job
```

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.7
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) >= 2.55
- An Azure subscription with Owner or User Access Administrator rights
- A resource group, storage account, and blob container for remote state (see below)

## Remote State Bootstrap

Each environment stores its Terraform state in Azure Blob Storage. Before running `terraform init` for the first time, create the remote-state storage resources once per project:

```bash
# Variables — adjust to your subscription
LOCATION="eastus"
STATE_RG="rg-marketing-tfstate"
STATE_SA="stmktgtfstate"          # must be globally unique, 3-24 lowercase alphanumeric
STATE_CONTAINER_DEV="tfstate-dev"
STATE_CONTAINER_TEST="tfstate-test"
STATE_CONTAINER_PROD="tfstate-prod"

az group create \
  --name "$STATE_RG" \
  --location "$LOCATION"

az storage account create \
  --name "$STATE_SA" \
  --resource-group "$STATE_RG" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2

for CONTAINER in $STATE_CONTAINER_DEV $STATE_CONTAINER_TEST $STATE_CONTAINER_PROD; do
  az storage container create \
    --name "$CONTAINER" \
    --account-name "$STATE_SA" \
    --auth-mode login
done
```

Update the `backend.tf` file in each environment with your `resource_group_name`, `storage_account_name`, and `container_name` values before running `terraform init`.

## Usage

### First-time initialisation

```bash
cd infra/environments/dev      # or test / prod

# Initialise Terraform and configure remote state
terraform init

# Review planned changes
terraform plan

# Apply
terraform apply
```

### Targeting a specific environment

Each environment is an independent Terraform root module. All three share the same modules, but each has its own state file and variable values.

```bash
# Dev
cd infra/environments/dev && terraform apply

# Test
cd infra/environments/test && terraform apply

# Prod
cd infra/environments/prod && terraform apply
```

## Environment Differences

| Setting | dev | test | prod |
|---|---|---|---|
| ACR SKU | Basic | Standard | Premium |
| PostgreSQL SKU | Standard_B1ms | Standard_B2ms | Standard_D4s_v3 |
| PostgreSQL HA | Disabled | Disabled | SameZone |
| PostgreSQL backup retention | 7 days | 7 days | 35 days |
| Service Bus SKU | Standard | Standard | Premium |
| Container Apps workload profile | Consumption | Consumption | D4 |
| Log Analytics retention | 30 days | 30 days | 90 days |
| Private networking | false | false | true |
| Key Vault purge protection | false | false | true |
| PostgreSQL password auth | true | true | false |

## Identity and RBAC

Three user-assigned managed identities are created per environment:

| Identity | Purpose |
|---|---|
| `<env>-api-identity` | API Container App |
| `<env>-worker-identity` | Worker Container App |
| `<env>-migration-identity` | Migration Container Apps Job |

RBAC assignments:

| Identity | Role | Scope |
|---|---|---|
| api, worker, migration | `AcrPull` | Azure Container Registry |
| api | `Azure Service Bus Data Sender` | Service Bus namespace |
| worker | `Azure Service Bus Data Receiver` | Service Bus namespace |
| api, worker, migration | `Key Vault Secrets User` | Key Vault |
| migration | `Key Vault Secrets Officer` | Key Vault |

## Outputs

Each environment exposes the following outputs for use by the GitHub Actions deployment workflow:

- `resource_group_name`
- `acr_login_server`
- `container_apps_environment_id`
- `frontend_app_fqdn`, `api_app_fqdn`
- `postgresql_fqdn`, `postgresql_database_name`
- `service_bus_namespace_fqdn`, `service_bus_queue_name`
- `key_vault_uri`
- `application_insights_connection_string`
- `api_identity_client_id`, `worker_identity_client_id`, `migration_identity_client_id`
