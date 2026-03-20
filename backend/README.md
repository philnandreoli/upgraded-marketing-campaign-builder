# Backend — Marketing Campaign Builder

The backend is split into two independent runtime processes:

| Process | Entry-point | Purpose |
|---------|-------------|---------|
| **API** | `uvicorn backend.apps.api.main:app` | Serves HTTP & WebSocket requests, enqueues workflow jobs |
| **Worker** | `python -m backend.worker` | Runs the AI agent pipeline, writes results to DB |

For local development both processes collapse into one when `WORKFLOW_EXECUTOR=in_process` (the default). See [Workflow Engine Runbook](WORKFLOW_ENGINE.md) for the worker reference.

## Running the API (local development)

```bash
# From the project root
pip install -r requirements.txt

# Canonical entry-point
uvicorn backend.apps.api.main:app --reload --port 8000
```

- **Interactive API docs:** http://localhost:8000/docs
- **Liveness probe:** `GET /health/live`
- **Readiness probe:** `GET /health/ready` (checks DB connection and executor readiness)

> **Legacy shim:** `uvicorn backend.main:app` still works via `backend/main.py` but the canonical form above is preferred and aligns with the container CMD.

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `AZURE_AI_PROJECT_ENDPOINT` | Your Azure AI Foundry project endpoint |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name (default: `gpt-4`) |

See the root [README](../README.md) for the full list of optional environment variables.

## API Startup Modes

The API supports two distinct startup behaviours controlled by the `API_AUTO_MIGRATE` environment variable.

### Local development (auto-migrate)

When `API_AUTO_MIGRATE=true` (the default when `DB_AUTH_MODE=local`), the API automatically applies any pending Alembic migrations via `alembic upgrade head` before accepting traffic.

**Expected local startup sequence:**

1. Start PostgreSQL (e.g. `docker compose up db`)
2. Start the API — migrations are applied automatically on startup
3. The API is ready to serve requests

No separate migration step is required. This makes the local feedback loop fast and self-contained.

### Cloud deployment (validate-only)

When `API_AUTO_MIGRATE=false` (the default when `DB_AUTH_MODE=azure`), the API does **not** mutate the schema. Instead it validates that the database is already at the expected Alembic head revision and **refuses to start** if the schema is mismatched.

Schema changes are applied exclusively by the dedicated migration job (`backend.apps.migrate.main`) which runs *before* the API and worker containers are started.

**Expected cloud deployment sequence:**

1. Build and push new container images
2. Run the migration job (`backend.apps.migrate.main`) — applies `alembic upgrade head`
3. Start / restart API and worker containers — startup validates schema compatibility
4. If schema validation fails the container exits with an error, preventing traffic from reaching an incompatible service

This separation keeps production schema changes auditable, repeatable, and decoupled from process restarts.

### Configuration reference

| Variable | Default | Description |
|----------|---------|-------------|
| `API_AUTO_MIGRATE` | derived from `DB_AUTH_MODE` | `true` = migrate on startup; `false` = validate only |

When `API_AUTO_MIGRATE` is not set the default is derived automatically:
- `DB_AUTH_MODE=local` (or unset) → `API_AUTO_MIGRATE` behaves as `true`
- `DB_AUTH_MODE=azure` → `API_AUTO_MIGRATE` behaves as `false`

## Agent Pipeline

When a new campaign is created, the **Coordinator Agent** orchestrates the following pipeline:

```
Strategy ➜ Content Creator ➜ Channel Planner ➜ Analytics ➜ Review/QA
                  ▲                                          │
                  └──────── Content Revision ◄───────────────┘
```

Each agent is a Python class that inherits from `BaseAgent` and communicates with Azure AI Foundry via the `LLMService`.

### Agent Descriptions

| Agent | File | Responsibility |
|-------|------|----------------|
| **Base Agent** | `agents/base_agent.py` | Abstract base class providing the `run()` method, LLM integration, and prompt structure that all agents inherit. |
| **Coordinator** | `agents/coordinator_agent.py` | Orchestrates the entire pipeline. Dispatches tasks to each agent in sequence, manages state transitions, handles the content-revision loop, and pauses for human approval when needed. Does **not** call the LLM itself. |
| **Strategy** | `agents/strategy_agent.py` | Analyses the campaign brief and produces objectives, target audience, value proposition, positioning, and key messages. Supports a clarification flow — it can ask the user follow-up questions when the brief has gaps before generating the full strategy. |
| **Content Creator** | `agents/content_creator_agent.py` | Generates marketing copy across multiple channels and formats: headlines, CTAs, social posts, email subjects/bodies, ad copy, and taglines. Produces A/B variants and tailors tone to each channel. |
| **Channel Planner** | `agents/channel_planner_agent.py` | Recommends the optimal marketing channel mix (email, social media, paid ads, SEO, etc.), budget allocation percentages, timing/cadence, and specific tactics for each channel. |
| **Analytics** | `agents/analytics_agent.py` | Defines the measurement framework: KPIs with quantifiable targets, tracking tools, reporting cadence, attribution model, and success criteria. |
| **Review / QA** | `agents/review_qa_agent.py` | Reviews the complete campaign for quality, brand consistency, and completeness. Produces section-level scores and a brand consistency score. Flags issues and suggestions, then triggers human-in-the-loop approval. |

### How Agents Work

1. Each agent defines a **system prompt** (its role and output schema), a **user prompt builder** (assembles campaign data into the prompt), and a **response parser** (validates the LLM JSON output).
2. The `BaseAgent.run()` method sends the prompts to the LLM and returns a structured `AgentResult`.
3. The Coordinator calls each agent in order, threading the growing campaign data through the pipeline.
4. After Review/QA, the Coordinator feeds review feedback back to the Content Creator for a revision pass.
5. Revised content is presented to the user for per-piece approval. Rejected pieces trigger another revision cycle (up to 3 rounds).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/campaigns` | Create a new campaign from a brief |
| `GET` | `/api/campaigns` | List all campaigns |
| `GET` | `/api/campaigns/{id}` | Get a campaign by ID |
| `DELETE` | `/api/campaigns/{id}` | Delete a campaign |
| `POST` | `/api/campaigns/{id}/clarify` | Submit answers to strategy clarification questions |
| `POST` | `/api/campaigns/{id}/content-approve` | Submit per-piece content approval decisions |
| `WS` | `/ws/campaigns/{id}` | WebSocket for real-time pipeline events |

> **Deprecated:** `/api/campaigns/{id}/review` and `/api/campaigns/{id}/review-clarify` return `410 Gone`. Use `/content-approve` instead.

## Rate Limiting

API rate limiting is implemented using [slowapi](https://github.com/laurents/slowapi) (application layer, per remote IP address). Limits are enforced per minute.

| Endpoint | Limit |
|----------|-------|
| Global (all `/api/*` routes) | 100 req/min |
| `POST /api/campaigns` | 10 req/min |
| Admin endpoints (`/api/admin/*`) | 30 req/min |
| `POST /api/ws/ticket` | 10 req/min |
| Health checks (`/health/*`) | Exempt |

When a limit is exceeded the API returns **HTTP 429 Too Many Requests** with a JSON body:

```json
{"error": "Rate limit exceeded: 10 per 1 minute"}
```

Rate limit response headers are included on **every** rate-limited response:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests allowed in the window |
| `X-RateLimit-Remaining` | Requests remaining before the limit is hit |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |
| `Retry-After` | Seconds until the client may retry |

## Project Structure

```
backend/
├── apps/
│   └── api/                  # FastAPI application boundary
│       ├── main.py           # Canonical entry-point (uvicorn backend.apps.api.main:app)
│       ├── dependencies.py   # RBAC helpers (Action, get_campaign_for_read/write)
│       ├── routers/          # Route handlers (campaigns, workflow, members, websocket)
│       ├── schemas/          # Request/response DTOs (campaigns.py, workflow.py)
│       └── startup.py        # App lifecycle hooks (DB init, executor setup)
├── core/                     # Cross-cutting concerns
│   ├── exceptions.py         # Domain exceptions
│   ├── rate_limit.py         # Shared slowapi Limiter instance
│   └── tracing.py            # OpenTelemetry bootstrap
├── infrastructure/           # External-facing adapters
│   ├── database.py           # SQLAlchemy async engine and session factory
│   ├── auth.py               # JWT validation (PyJWT, OIDC)
│   ├── campaign_store.py     # Campaign persistence
│   ├── executors/            # Workflow executor implementations (in_process, azure_service_bus)
│   └── llm/                  # Azure AI Foundry LLM integration
├── application/              # Use-case orchestration
│   └── campaign_workflow_service.py
├── orchestration/            # AI agent pipeline
│   ├── coordinator_agent.py  # Orchestrates the full pipeline
│   ├── strategy_agent.py
│   ├── content_creator_agent.py
│   ├── channel_planner_agent.py
│   ├── analytics_agent.py
│   └── review_qa_agent.py
├── agents/                   # Backward-compat shims → orchestration/
├── api/                      # Backward-compat shims → apps/api/
├── services/                 # Backward-compat shims → infrastructure/
├── models/                   # Pydantic models & SQLAlchemy ORM models
├── migrations/               # Alembic database migrations
├── tests/                    # pytest test suite
├── worker.py                 # Standalone worker process (python -m backend.worker)
├── main.py                   # Compat shim → apps/api/main.py
├── config.py                 # Pydantic-settings configuration
├── Containerfile             # Container build definition (preferred)
└── Dockerfile                # Docker build definition
```

## Canonical Backend Import Boundaries

To keep runtime and tests aligned, dependencies for auth/store/database must use
the canonical `backend.infrastructure.*` modules:

- `backend.infrastructure.auth`
- `backend.infrastructure.database`
- `backend.infrastructure.campaign_store`

`backend.services.*` remains a backward-compatibility shim surface for legacy
imports, but new or refactored runtime/test code should import from
`backend.infrastructure.*` directly.

## Running Tests

```bash
# From the project root
AZURE_AI_PROJECT_ENDPOINT=https://placeholder.example.com python -m pytest backend/tests/
```

Tests use `pytest-asyncio` and are located in `backend/tests/`. The test suite includes unit tests for agents, API routes, models, the campaign store, and the LLM service.

### Key Test Configuration

- `asyncio_mode = auto` — async tests run without explicit decorators
- Test paths are set to `backend/tests` in `pytest.ini`

## Foundry Agent Operations

When `FOUNDRY_AGENTS_ENABLED=true`, the backend registers each marketing agent as an **AI Foundry Agent version** on startup via `services/agent_registry.py`. This gives you:

- Server-side agent identity and versioning
- Visibility in the Azure AI Foundry portal
- Automatic reuse of existing agent versions (creates new ones only when needed)

If registration fails for any agent, it falls back to direct LLM calls transparently.

## Configuration

All settings are loaded from environment variables (or a `.env` file) using **pydantic-settings**. A complete reference is available in `.env.example`. The configuration is defined in `config.py` and organised into:

| Settings class | Key variables |
|----------------|---------------|
| `AzureAIProjectSettings` | `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME` |
| `AgentSettings` | `AGENT_TEMPERATURE`, `AGENT_MAX_TOKENS`, `AGENT_MAX_RETRIES`, `PIPELINE_IDLE_TIMEOUT_DAYS` |
| `TracingSettings` | `TRACING_ENABLED`, `TRACING_EXPORTER`, `OTLP_ENDPOINT`, `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| `OIDCSettings` | `AUTH_ENABLED`, `OIDC_AUTHORITY`, `OIDC_CLIENT_ID` |
| `FoundryAgentsSettings` | `FOUNDRY_AGENTS_ENABLED` |
| `CORSSettings` | `CORS_ALLOWED_ORIGINS` |
| `AppSettings` | `APP_ENV`, `APP_PORT`, `APP_LOG_LEVEL`, `WORKFLOW_EXECUTOR` |
| `ServiceBusSettings` | `AZURE_SERVICE_BUS_NAMESPACE`, `AZURE_SERVICE_BUS_CONNECTION_STRING`, `AZURE_SERVICE_BUS_QUEUE_NAME` |
| `WorkerSettings` | `WORKER_MAX_CONCURRENCY`, `WORKER_SHUTDOWN_TIMEOUT_SECONDS`, `WORKER_HEALTH_PORT` |
| `EventSettings` | `EVENT_CHANNEL_NAME` (PostgreSQL NOTIFY channel for worker → API relay) |
| `DatabaseSettings` | `DB_AUTH_MODE`, `DATABASE_URL`, `AZURE_POSTGRES_HOST/DATABASE/USER`, `API_AUTO_MIGRATE` |

### Authentication configuration

`AUTH_ENABLED` controls JWT/OIDC authentication for all campaign API endpoints.

| Environment | Required value | Notes |
|-------------|----------------|-------|
| Local development | `false` | Auth can be disabled for convenience |
| Test / CI | `false` | Allowed so automated pipelines can run without tokens |
| Staging / Production | `true` | **Mandatory** — leaving this `false` exposes all endpoints |

> **Important:** The API **refuses to start** if `APP_ENV` is not `development` or `test` and `AUTH_ENABLED=false`. Always set `AUTH_ENABLED=true` before deploying to any shared or production environment.

When `AUTH_ENABLED=true` you must also configure `OIDC_AUTHORITY` and `OIDC_CLIENT_ID` so the API can validate bearer tokens.

### CORS configuration

`CORS_ALLOWED_ORIGINS` controls which browser origins may make cross-origin requests to the API.

| Environment | Required value | Example |
|-------------|----------------|---------|
| Local development | `["*"]` (default) | No change needed |
| Staging / Production | Explicit JSON array | `CORS_ALLOWED_ORIGINS='["https://app.example.com"]'` |

> **Important:** The API **refuses to start** if `APP_ENV` is not `development` and `CORS_ALLOWED_ORIGINS` still contains the wildcard `"*"`.  Always set explicit origins before deploying.

When the React frontend is served by the same nginx reverse-proxy that proxies API traffic (the default production topology), the browser sees a single origin so CORS is not exercised at all.  Restricting allowed origins is most important when the API is accessed directly from a different origin (e.g. a separate staging frontend or a developer machine).
