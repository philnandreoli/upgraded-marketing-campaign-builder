# Marketing Campaign Builder

An AI-powered multi-agent system for building comprehensive marketing campaigns. A conversational UI guides users through campaign creation while a pipeline of specialised AI agents collaborates behind the scenes to produce strategy, content, channel plans, analytics frameworks, and quality reviews.

The platform supports **multi-tenant workspaces** with role-based access control, **real-time pipeline tracking** via WebSocket, **per-content-piece approval workflows**, and a full **infrastructure-as-code** deployment to Azure.

## Architecture Overview

### Split Backend Model

The backend is split into two independently deployable runtime processes:

- **API process** (`backend.apps.api.main:app`) — handles HTTP and WebSocket requests, enqueues workflow jobs, and relays real-time pipeline events back to the browser.
- **Worker process** (`python -m backend.worker`) — picks up workflow jobs from Azure Service Bus and runs the `CoordinatorAgent` pipeline, writing results back to the database.

For local development the two processes collapse into one: the API runs the pipeline inline (`WORKFLOW_EXECUTOR=in_process`, the default). No worker or Service Bus is required.

```
┌──────────────┐      WebSocket / REST      ┌──────────────────────────┐
│   React SPA  │  ◄────────────────────►    │   FastAPI API Process    │
│  (Vite)      │      :5173 ► :8000         │  (backend.apps.api.main) │
└──────────────┘                            └──────────┬───────────────┘
                                                       │ azure_service_bus mode
                                                       │ (enqueues WorkflowJob)
                                            ┌──────────▼───────────────┐
                                            │   Azure Service Bus      │
                                            │   (workflow-jobs queue)  │
                                            └──────────┬───────────────┘
                                                       │
                                            ┌──────────▼───────────────┐
                                            │   Worker Process         │
                                            │   (backend.worker)       │
                                            │   Coordinator            │
                                            │    ├─ Strategy           │
                                            │    ├─ Content            │
                                            │    ├─ Channel            │
                                            │    ├─ Analytics          │
                                            │    └─ Review/QA          │
                                            └──────────┬───────────────┘
                                                       │
                                            ┌──────────▼───────────────┐
                                            │   Azure AI Foundry       │
                                            │   (LLM endpoint)         │
                                            └──────────────────────────┘
```

### Technology Stack

| Layer | Tech |
|-------|------|
| Frontend | React 19, React Router 7, Vite 7, MSAL (Azure AD auth) |
| API process | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) |
| Worker process | Python 3.12 (`python -m backend.worker`) |
| AI | Azure AI Foundry SDK, GPT-4 (configurable) |
| Database | PostgreSQL via asyncpg + Alembic migrations |
| Cache / Tickets | Redis (ticket store for async operations) |
| Auth | Azure Entra ID (OIDC / JWT), MSAL browser + backend validation |
| Observability | OpenTelemetry → console, OTLP, or Azure Monitor |
| Rate Limiting | Slowapi per-user / per-IP rate limiting |
| IaC | Terraform — `infra/` (VNet, Container Apps, Postgres, Service Bus, Key Vault) |
| Containers | Podman / Docker — `deploy/api.Dockerfile`, `deploy/worker.Dockerfile`, `frontend/Containerfile` |
| CI/CD | GitHub Actions — backend-api, backend-worker, frontend, deploy, terraform |
| Dev Container | VS Code Dev Container with PostgreSQL + Redis sidecars |

## Features

- **Multi-workspace tenancy** — create workspaces, invite members, and organise campaigns
- **Role-based access control** — three-tier RBAC: platform roles (Admin / Campaign Builder / Viewer), workspace roles (Creator / Contributor / Viewer), and campaign roles (Owner / Editor / Viewer)
- **AI agent pipeline** — six specialised agents (Strategy → Content → Channel Planner → Analytics → Review/QA) orchestrated by a Coordinator
- **Human-in-the-loop** — clarification questions before strategy generation; per-content-piece approval/rejection with revision cycles
- **Real-time updates** — WebSocket streams pipeline events to the browser as each agent completes
- **Dashboard with filtering** — search, filter by status, and saved views for campaign management
- **Dark / light theme** — user-toggleable UI theme
- **Admin panel** — user management and provisioning
- **Durable workflows** — checkpoint-based pipeline state; resume after interruption, retry on failure
- **Optimistic locking** — prevents concurrent edit conflicts
- **Auto-aging** — campaigns idle for 30+ days are automatically failed

## Prerequisites

- **Node.js** ≥ 18 and **npm**
- **Python** ≥ 3.12 and **pip**
- An **Azure AI Foundry** project endpoint (or compatible OpenAI-style endpoint)
- *(Optional)* PostgreSQL if you want persistent storage
- *(Optional)* Redis for the async ticket store
- *(Optional)* Podman or Docker for containerised deployment

> **Tip:** A ready-to-use [Dev Container](#dev-container) configuration is included — it installs all dependencies and starts PostgreSQL and Redis automatically.

## Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Key variables (see `.env.example` for the full reference):

```bash
# Required — Azure AI Foundry
AZURE_AI_PROJECT_ENDPOINT=https://<your-endpoint>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4   # or your deployment name

# Optional — Authentication (required in production)
AUTH_ENABLED=false                 # enable JWT validation
OIDC_AUTHORITY=https://login.microsoftonline.com/<tenant>/v2.0
OIDC_CLIENT_ID=<app-id>

# Optional — Agent behaviour
AGENT_TEMPERATURE=0.7
AGENT_MAX_TOKENS=4096
AGENT_MAX_RETRIES=3

# Optional — Tracing
TRACING_ENABLED=false
TRACING_EXPORTER=console          # console | otlp | azure_monitor
OTLP_ENDPOINT=http://localhost:4317
APPLICATIONINSIGHTS_CONNECTION_STRING=

# Optional — Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/campaigns
DB_AUTH_MODE=local                # local (password) | azure (managed identity)
API_AUTO_MIGRATE=true             # auto-apply migrations on startup

# Optional — Workflow execution
WORKFLOW_EXECUTOR=in_process      # in_process | azure_service_bus

# Optional — App
APP_ENV=development
APP_PORT=8000
APP_LOG_LEVEL=INFO
CORS_ALLOWED_ORIGINS=["*"]        # restrict in production
```

## Quick Start

### 1. Backend (API process)

```bash
# Install Python dependencies (from the project root)
pip install -r requirements.txt

# Run the API server — canonical entry-point
uvicorn backend.apps.api.main:app --reload --port 8000
```

The API is available at **http://localhost:8000** with interactive docs at `/docs`.

Health probes: `GET /health/live` (liveness) and `GET /health/ready` (readiness).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open **http://localhost:5173** in your browser. The API must be running on port 8000.

### 3. Dev Container

The project includes a VS Code Dev Container (`.devcontainer/`) that:
- Uses Python 3.12 on Debian Bookworm
- Starts a **PostgreSQL 16** sidecar and a **Redis** sidecar
- Installs the Azure CLI, Python dependencies, Node.js, and frontend packages automatically
- Forwards ports **5432** (Postgres), **6379** (Redis), **8000** (backend), and **5173** (frontend)

Open the project in VS Code and select **Reopen in Container**, or use the GitHub Codespaces button.

### 4. Container Deployment (optional)

```bash
podman-compose up --build
```

This starts three services — the frontend on **http://localhost:3000**, the backend API on **http://localhost:8000**, and a standalone **worker** process that processes pipeline jobs from Azure Service Bus.

> **Note:** The worker service requires `WORKFLOW_EXECUTOR=azure_service_bus` and valid Azure Service Bus credentials in your `.env` file. See [Worker Topology](#worker-topology) for details.

## Agent Pipeline

When a campaign is launched the **Coordinator Agent** orchestrates the following pipeline:

```
Strategy ➜ Content Creator ➜ Channel Planner ➜ Analytics ➜ Review/QA
                  ▲                                          │
                  └──────── Content Revision ◄───────────────┘
```

| Agent | Responsibility |
|-------|----------------|
| **Strategy** | Analyses the brief; produces objectives, target audience, positioning, and key messages. Can ask the user clarification questions. |
| **Content Creator** | Generates marketing copy across channels and formats with A/B variants. |
| **Channel Planner** | Recommends channel mix, budget allocation, timing, and per-channel tactics. |
| **Analytics** | Defines KPIs, tracking tools, reporting cadence, and attribution model. |
| **Review / QA** | Scores quality and brand consistency; flags issues; triggers human-in-the-loop approval. |
| **Coordinator** | Dispatches tasks to each agent in sequence, manages state transitions, and handles the content-revision loop. |

Each agent inherits from `BaseAgent` and communicates with Azure AI Foundry via the `LLMService`.

## Authorization Model

Access is enforced at three levels:

| Scope | Roles | Description |
|-------|-------|-------------|
| **Platform** | Admin, Campaign Builder, Viewer | Global capabilities — admins have full access, viewers are read-only everywhere |
| **Workspace** | Creator, Contributor, Viewer | Per-workspace — creators can manage members and campaigns |
| **Campaign** | Owner, Editor, Viewer | Per-campaign — owners have full control, editors can modify content |

Workspace roles serve as a fallback when no explicit campaign membership exists. Platform viewers are capped at read-only regardless of workspace or campaign role. Missing membership returns 404 to avoid leaking campaign existence.

## Worker Topology

The application supports two execution modes controlled by the `WORKFLOW_EXECUTOR` environment variable:

### Local development — `in_process` (default)

```
React SPA  ──►  FastAPI API (backend.apps.api.main:app)
                   └─ CoordinatorAgent runs inline (no worker needed)
```

The API runs the pipeline directly in the same process. No additional services are needed. This is the default for local development and the Dev Container.

### Production — `azure_service_bus` + standalone worker

```
React SPA  ──►  FastAPI API  ──►  Azure Service Bus  ──►  Worker  ──►  DB
                   (enqueues job)       (queue)          (runs pipeline)
```

The API enqueues a `WorkflowJob` message and returns immediately. A separate worker process (`backend/worker.py`) picks up jobs from the Service Bus queue and runs the `CoordinatorAgent` pipeline, writing results back to the database. Events are relayed back to the API via a PostgreSQL `NOTIFY` channel.

| Setting | Local dev | Production |
|---------|-----------|------------|
| `WORKFLOW_EXECUTOR` | `in_process` | `azure_service_bus` |
| Worker process | Not needed | `python -m backend.worker` |
| Azure Service Bus | Not needed | Required |
| Event relay | In-process `asyncio.Future` | PostgreSQL NOTIFY (`workflow_events`) |

**Starting the worker manually:**

```bash
export WORKFLOW_EXECUTOR=azure_service_bus
python -m backend.worker
```

**Worker-specific settings** (see `.env.example`):

```bash
WORKER_MAX_CONCURRENCY=3            # max simultaneous pipeline executions
WORKER_SHUTDOWN_TIMEOUT_SECONDS=300 # graceful shutdown wait time
WORKER_HEALTH_PORT=8001             # health endpoint port (/health/live, /health/ready)
```

See the [workflow-engine runbook](backend/WORKFLOW_ENGINE.md) for a full operator reference.

## API Startup Modes

The API supports two startup behaviours controlled by `API_AUTO_MIGRATE`:

- **Local development (`API_AUTO_MIGRATE=true`, default when `DB_AUTH_MODE=local`)** — automatically applies pending Alembic migrations on startup. No separate migration step needed.
- **Cloud deployment (`API_AUTO_MIGRATE=false`, default when `DB_AUTH_MODE=azure`)** — validates the database is at the expected Alembic head but does **not** mutate the schema. Migrations are applied by the dedicated migration job (`backend.apps.migrate.main`) before containers are started.

## API Endpoints

### Core Resources

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/me` | Current user profile |
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (checks DB + executor) |

### Workspaces

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/workspaces` | Create workspace |
| `GET` | `/api/workspaces` | List user's workspaces |
| `PATCH` | `/api/workspaces/{id}` | Update workspace |
| `DELETE` | `/api/workspaces/{id}` | Delete workspace |
| `GET/POST/PATCH/DELETE` | `/api/workspaces/{id}/members` | Workspace member management |

### Campaigns

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/workspaces/{ws_id}/campaigns` | Create campaign |
| `GET` | `/api/workspaces/{ws_id}/campaigns` | List campaigns (paginated) |
| `GET` | `/api/workspaces/{ws_id}/campaigns/{id}` | Get campaign details |
| `PATCH` | `/api/workspaces/{ws_id}/campaigns/{id}` | Update draft campaign |
| `DELETE` | `/api/workspaces/{ws_id}/campaigns/{id}` | Delete campaign |
| `GET` | `/api/workspaces/{ws_id}/campaigns/{id}/events` | Campaign event log |
| `GET/POST/PATCH/DELETE` | `/api/workspaces/{ws_id}/campaigns/{id}/members` | Campaign member management |

### Pipeline Control

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `.../campaigns/{id}/launch` | Start the agent pipeline |
| `POST` | `.../campaigns/{id}/clarify` | Submit clarification answers |
| `POST` | `.../campaigns/{id}/content-approve` | Approve all content |
| `PATCH` | `.../campaigns/{id}/content/{idx}/decision` | Per-piece approval decision |
| `PATCH` | `.../campaigns/{id}/content/{idx}/notes` | Add content notes |
| `POST` | `.../campaigns/{id}/resume` | Resume paused pipeline |
| `POST` | `.../campaigns/{id}/retry` | Retry failed stage |

### Real-Time

| Protocol | Path | Description |
|----------|------|-------------|
| `WebSocket` | `/ws/campaigns/{id}` | Real-time pipeline event stream |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST/PATCH` | `/api/admin/users` | User management and provisioning |

Interactive API documentation is available at `/docs` when the server is running.

## Frontend Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Campaign list with search, status filters, and saved views |
| `/workspaces` | Workspace List | Browse and create workspaces |
| `/workspaces/:id` | Workspace Detail | Workspace campaigns and members |
| `/workspaces/:id/settings` | Workspace Settings | Workspace configuration (builders only) |
| `/new` | New Campaign | Campaign creation wizard |
| `/workspaces/:wsId/campaigns/new` | New Campaign | Create campaign within a workspace |
| `/workspaces/:wsId/campaigns/:id/edit` | Edit Campaign | Edit a draft campaign |
| `/workspaces/:wsId/campaigns/:id` | Campaign Detail | Real-time pipeline view with split/focus layout modes |
| `/admin` | Admin Panel | User management (admins only) |

## Running Tests

```bash
# Backend tests (from the project root)
AZURE_AI_PROJECT_ENDPOINT=https://placeholder.example.com python -m pytest backend/tests/

# Frontend tests
cd frontend && npm test

# Frontend linting and build validation
cd frontend && npm run lint && npm run build
```

The backend test suite includes 35+ test files covering API routes, agents, RBAC, WebSocket, workflow execution, event pub/sub, database auth, CORS, rate limiting, optimistic locking, and startup validation.

The frontend test suite includes 11 Vitest test files covering all pages, contexts, and key components.

## CI/CD

GitHub Actions workflows in `.github/workflows/`:

| Workflow | File | Trigger |
|----------|------|---------|
| Backend API | `backend-api.yml` | Build, lint, and test the API |
| Backend Worker | `backend-worker.yml` | Build, lint, and test the worker |
| Backend Shared | `backend-shared.yml` | Shared backend CI steps |
| Frontend | `frontend.yml` | Build, lint, and test the React SPA |
| Deploy | `deploy.yml` | Container deployment to Azure Container Apps |
| Terraform | `terraform.yml` | Infrastructure provisioning for dev / test / prod |

## Infrastructure as Code

The `infra/` directory contains Terraform configuration for provisioning Azure resources across three environments (`dev`, `test`, `prod`):

| Module | Resources |
|--------|-----------|
| `networking` | VNet, subnets, NSGs, private DNS zones |
| `monitoring` | Log Analytics workspace, Application Insights |
| `container_registry` | Azure Container Registry |
| `postgresql` | Azure Database for PostgreSQL Flexible Server |
| `service_bus` | Azure Service Bus namespace + workflow-jobs queue |
| `key_vault` | Azure Key Vault (RBAC mode) |
| `identities` | Managed identities + RBAC assignments |
| `container_apps` | Container Apps Environment, API + worker apps, migration job |

See the [infrastructure README](infra/README.md) for prerequisites and deployment instructions.

## Project Structure

```
marketing-campaign-builder/
├── backend/                      # Python backend (API + worker)
│   ├── apps/
│   │   ├── api/                  # FastAPI application boundary
│   │   │   ├── main.py           # Canonical entry-point
│   │   │   ├── dependencies.py   # Dependency injection
│   │   │   ├── routers/          # Route handlers
│   │   │   ├── schemas/          # Request/response DTOs
│   │   │   └── startup.py        # App lifecycle hooks
│   │   ├── migrate/              # Standalone migration runner
│   │   └── worker/               # Worker app entry-point
│   ├── core/                     # Cross-cutting concerns (exceptions, tracing, rate limiting)
│   ├── infrastructure/           # DB, auth, stores, executors, LLM service
│   │   └── executors/            # InProcess + AzureServiceBus executors
│   ├── application/              # Campaign workflow service (business logic)
│   ├── orchestration/            # CoordinatorAgent and pipeline agents
│   ├── models/                   # Pydantic models (campaign, user, workspace, workflow, events)
│   ├── migrations/               # Alembic database migrations (12 versions)
│   ├── tests/                    # pytest test suite (35+ test files)
│   ├── agents/                   # Backward-compat shims → orchestration/
│   ├── api/                      # Backward-compat shims → apps/api/
│   ├── services/                 # Backward-compat shims → infrastructure/
│   ├── worker.py                 # Standalone worker process
│   ├── main.py                   # Compat shim → apps/api/main.py
│   └── config.py                 # Pydantic-settings configuration
├── frontend/                     # React SPA
│   ├── src/
│   │   ├── components/           # 19 UI components (pipeline, content, review, workspace, etc.)
│   │   ├── hooks/                # useWebSocket, useTheme, useSavedViews
│   │   ├── pages/                # 7 pages (Dashboard, CampaignDetail, NewCampaign, Workspaces, Admin)
│   │   ├── constants/            # Status groups and enums
│   │   ├── test/                 # 11 Vitest test files
│   │   ├── UserContext.jsx       # Auth / user state
│   │   ├── WorkspaceContext.jsx  # Active workspace state
│   │   ├── api.js                # Backend API client
│   │   └── authConfig.js         # MSAL configuration
│   ├── Containerfile             # Container build (preferred)
│   └── Dockerfile                # Docker build
├── infra/                        # Terraform infrastructure as code
│   ├── environments/             # dev / test / prod root modules
│   └── modules/                  # Reusable modules (networking, postgres, service_bus, etc.)
├── deploy/
│   ├── api.Dockerfile            # API container
│   ├── worker.Dockerfile         # Worker container
│   └── migration.Dockerfile      # Migration job container
├── .devcontainer/                # VS Code Dev Container + Postgres/Redis sidecars
├── .github/workflows/            # CI/CD pipelines (6 workflows)
├── .env.example                  # Reference environment variables
├── podman-compose.yml            # Container orchestration (frontend + api + worker)
├── requirements.txt              # Python dependencies
└── pytest.ini                    # Test configuration
```

## Further Reading

- [Backend README](backend/README.md) — API startup modes, agent descriptions, pipeline details
- [Frontend README](frontend/README.md) — component catalogue, hooks, and project structure
- [Workflow Engine Runbook](backend/WORKFLOW_ENGINE.md) — operator reference for the worker and pipeline
- [Infrastructure README](infra/README.md) — Terraform modules and Azure deployment
