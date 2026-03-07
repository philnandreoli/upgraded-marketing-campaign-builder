# Marketing Campaign Builder

An AI-powered multi-agent system that helps you build comprehensive marketing campaigns. A conversational UI guides you through campaign creation while a pipeline of specialised AI agents collaborates behind the scenes to produce strategy, content, channel plans, analytics frameworks, and quality reviews.

## Architecture Overview

```
┌──────────────┐        WebSocket / REST        ┌──────────────────┐
│   React SPA  │  ◄──────────────────────────►  │  FastAPI Backend  │
│  (Vite)      │        :5173 ► :8000           │                  │
└──────────────┘                                 │  Coordinator     │
                                                 │   ├─ Strategy    │
                                                 │   ├─ Content     │
                                                 │   ├─ Channel     │
                                                 │   ├─ Analytics   │
                                                 │   └─ Review/QA   │
                                                 └────────┬─────────┘
                                                          │
                                                 ┌────────▼─────────┐
                                                 │  Azure AI Foundry │
                                                 │  (LLM endpoint)   │
                                                 └──────────────────┘
```

| Layer | Tech |
|-------|------|
| Frontend | React 19, React Router 7, Vite 7 |
| Backend | Python 3, FastAPI, Pydantic v2 |
| AI | Azure AI Foundry SDK, GPT-4 (configurable) |
| Database | PostgreSQL via SQLAlchemy (async) + Alembic migrations |
| Observability | OpenTelemetry, Azure Monitor (optional) |
| Containers | Podman / Docker via `podman-compose.yml` |
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

### 1. Backend

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run the API server
uvicorn backend.main:app --reload --port 8000
```

The API is available at **http://localhost:8000** with docs at `/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open **http://localhost:5173** in your browser.

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
React SPA  ──►  FastAPI Backend
                   └─ CoordinatorAgent runs inline (no worker needed)
```

The API runs the pipeline directly in the same process. No additional services are needed. This is the default for local development and the Dev Container.

### Production — `azure_service_bus` + standalone worker

```
React SPA  ──►  FastAPI API  ──►  Azure Service Bus  ──►  Worker  ──►  DB
                   (enqueues job)       (queue)          (runs pipeline)
```

The API enqueues a `WorkflowJob` message and returns immediately. A separate worker process (`backend/worker.py`) picks up jobs from the Service Bus queue and runs the `CoordinatorAgent` pipeline, writing results back to the database.

| Setting | Local dev | Production |
|---------|-----------|------------|
| `WORKFLOW_EXECUTOR` | `in_process` | `azure_service_bus` |
| Worker process | Not needed | `python -m backend.worker` |
| Azure Service Bus | Not needed | Required |

**Starting the worker manually:**

```bash
WORKFLOW_EXECUTOR=azure_service_bus python -m backend.worker
```

**Worker-specific settings** (see `.env.example`):

```bash
WORKER_MAX_CONCURRENCY=3           # max simultaneous pipeline executions
WORKER_SHUTDOWN_TIMEOUT_SECONDS=300 # graceful shutdown wait time
WORKER_HEALTH_PORT=8001            # health endpoint port (/health/live, /health/ready)
```

## Running Tests

```bash
# Backend tests
pytest

# Frontend linting
cd frontend && npm run lint
```

## Project Structure

```
marketing-campaign-builder/
├── backend/              # FastAPI application & AI agents
│   ├── agents/           # Specialised AI agents (strategy, content, etc.)
│   ├── api/              # REST & WebSocket endpoints
│   ├── models/           # Pydantic models & DB schemas
│   ├── services/         # LLM service, campaign store, tracing
│   ├── migrations/       # Alembic database migrations
│   └── tests/            # pytest test suite
├── frontend/             # React SPA
│   └── src/
│       ├── components/   # UI components (strategy, content, review, etc.)
│       ├── hooks/        # Custom React hooks (WebSocket, theme)
│       └── pages/        # Route-level page components
├── .devcontainer/        # VS Code Dev Container config + Postgres sidecar
├── .env.example          # Reference environment variables
├── podman-compose.yml    # Container orchestration
├── requirements.txt      # Python dependencies
└── pytest.ini            # Test configuration
```

See the [backend README](backend/README.md) and [frontend README](frontend/README.md) for more details on each layer.
