# Marketing Campaign Builder

An AI-powered multi-agent system that helps you build comprehensive marketing campaigns. A conversational UI guides you through campaign creation while a pipeline of specialised AI agents collaborates behind the scenes to produce strategy, content, channel plans, analytics frameworks, and quality reviews.

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

| Layer | Tech |
|-------|------|
| Frontend | React 19, React Router 7, Vite 7 |
| API process | Python 3, FastAPI, Pydantic v2 (`backend.apps.api.main:app`) |
| Worker process | Python 3 (`python -m backend.worker`) |
| AI | Azure AI Foundry SDK, GPT-4 (configurable) |
| Database | PostgreSQL via SQLAlchemy (async) + Alembic migrations |
| Observability | OpenTelemetry, Azure Monitor (optional) |
| Containers | Podman / Docker — `deploy/api.Dockerfile`, `deploy/worker.Dockerfile`, `frontend/Containerfile` |
| CI | GitHub Actions — `.github/workflows/ci.yml` |
| Dev Container | VS Code Dev Container with PostgreSQL sidecar |

## Prerequisites

- **Node.js** ≥ 18 and **npm**
- **Python** ≥ 3.12 and **pip**
- An **Azure AI Foundry** project endpoint (or compatible OpenAI-style endpoint)
- *(Optional)* PostgreSQL if you want persistent storage
- *(Optional)* Podman or Docker for containerised deployment

> **Tip:** A ready-to-use [Dev Container](#dev-container) configuration is included — it installs all dependencies and starts a PostgreSQL instance automatically.

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

# Optional — Agent behaviour
AGENT_TEMPERATURE=0.7
AGENT_MAX_TOKENS=4096
AGENT_MAX_RETRIES=3

# Optional — Tracing
TRACING_ENABLED=false
TRACING_EXPORTER=console          # console | otlp | azure_monitor
OTLP_ENDPOINT=http://localhost:4317
APPLICATIONINSIGHTS_CONNECTION_STRING=
TRACING_CONTENT_RECORDING=true

# Optional — Foundry Agent Operations
FOUNDRY_AGENTS_ENABLED=false      # register agents as Foundry Agent versions

# Optional — App
APP_ENV=development
APP_PORT=8000
APP_LOG_LEVEL=INFO

# Optional — Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/campaigns
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
- Starts a **PostgreSQL 16** sidecar (user: `postgres`, password: `postgres`, db: `campaigns`)
- Installs the Azure CLI, Python dependencies, Node.js, and frontend packages automatically
- Forwards ports **5432** (Postgres), **8000** (backend), and **5173** (frontend)

Open the project in VS Code and select **Reopen in Container**, or use the GitHub Codespaces button.

### 4. Container Deployment (optional)

```bash
podman-compose up --build
```

This starts three services — the frontend on **http://localhost:3000**, the backend API on **http://localhost:8000**, and a standalone **worker** process that processes pipeline jobs from Azure Service Bus.

> **Note:** The worker service requires `WORKFLOW_EXECUTOR=azure_service_bus` and valid Azure Service Bus credentials in your `.env` file. See [Worker Topology](#worker-topology) for details.

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

## Running Tests

```bash
# Backend tests (from the project root)
AZURE_AI_PROJECT_ENDPOINT=https://placeholder.example.com python -m pytest backend/tests/

# Frontend linting and build validation
cd frontend && npm run lint && npm run build
```

## Project Structure

```
marketing-campaign-builder/
├── backend/                  # Python backend (API + worker)
│   ├── apps/
│   │   └── api/              # FastAPI application boundary
│   │       ├── main.py       # Canonical entry-point (uvicorn backend.apps.api.main:app)
│   │       ├── dependencies.py
│   │       ├── routers/      # Route handlers
│   │       ├── schemas/      # Request/response DTOs
│   │       └── startup.py    # App lifecycle hooks
│   ├── core/                 # Cross-cutting concerns (exceptions, tracing)
│   ├── infrastructure/       # DB, auth, campaign store, executors, LLM
│   ├── application/          # Campaign workflow service
│   ├── orchestration/        # CoordinatorAgent and pipeline agents
│   ├── agents/               # Backward-compat shims → orchestration/
│   ├── api/                  # Backward-compat shims → apps/api/
│   ├── services/             # Backward-compat shims → infrastructure/
│   ├── models/               # Pydantic models & DB schemas
│   ├── migrations/           # Alembic database migrations
│   ├── tests/                # pytest test suite
│   ├── worker.py             # Standalone worker process (python -m backend.worker)
│   ├── main.py               # Compat shim → apps/api/main.py
│   └── config.py             # Pydantic-settings configuration
├── frontend/                 # React SPA
│   ├── src/
│   │   ├── components/       # UI components (strategy, content, review, etc.)
│   │   ├── hooks/            # Custom React hooks (WebSocket, theme)
│   │   └── pages/            # Route-level page components
│   ├── Containerfile         # Container build definition (preferred)
│   └── Dockerfile            # Docker build definition
├── deploy/
│   ├── api.Dockerfile        # API container build definition
│   └── worker.Dockerfile     # Worker container build definition
├── docs/
│   └── planning/
│       └── backend-split/    # Architecture planning documents
├── .devcontainer/            # VS Code Dev Container config + Postgres sidecar
├── .env.example              # Reference environment variables
├── podman-compose.yml        # Container orchestration (frontend + api + worker)
├── requirements.txt          # Python dependencies
└── pytest.ini                # Test configuration
```

See the [backend README](backend/README.md), [workflow-engine runbook](backend/WORKFLOW_ENGINE.md), and [frontend README](frontend/README.md) for per-layer details.
