# Workflow Engine — Runbook

The workflow engine is the **worker process** that runs the AI agent pipeline. It is a separate Python process (`backend/worker.py`) that picks up `WorkflowJob` messages from an Azure Service Bus queue and executes the `CoordinatorAgent` pipeline, writing results back to the database.

In local development the workflow engine runs **in-process** inside the API — no separate worker or Service Bus is needed.

---

## Execution Modes

The active mode is controlled by the `WORKFLOW_EXECUTOR` environment variable.

### `in_process` (default — local development)

```
React SPA  ──►  FastAPI API (backend.apps.api.main:app)
                   └─ CoordinatorAgent runs inline, same process
```

- No additional services required.
- Pipeline results are streamed directly to the WebSocket via an in-process `asyncio.Future`.
- Default for local development and the VS Code Dev Container.

### `azure_service_bus` (production)

```
React SPA  ──►  FastAPI API ──►  Azure Service Bus ──►  Worker ──►  DB
                 (enqueues)          (queue)           (pipeline)
                                                           │
                                               PostgreSQL NOTIFY ──►  API WebSocket relay
```

- The API enqueues a `WorkflowJob` and returns immediately (`202 Accepted`).
- The worker picks up the job, runs `CoordinatorAgent`, and writes checkpoints and events to the database.
- Real-time events are relayed back to the API (and then to the browser) via a PostgreSQL `NOTIFY` channel (`EVENT_CHANNEL_NAME`, default `workflow_events`).

---

## Running the Worker Locally

> **Prerequisites:** Azure Service Bus namespace or connection string, and a PostgreSQL database accessible at `DATABASE_URL`.

```bash
# 1. Set required variables in .env or export them directly
export WORKFLOW_EXECUTOR=azure_service_bus
export AZURE_AI_PROJECT_ENDPOINT=https://<your-endpoint>

# One of the following for Service Bus authentication:
export AZURE_SERVICE_BUS_NAMESPACE=<yourbus>.servicebus.windows.net   # managed identity / DefaultAzureCredential
# OR
export AZURE_SERVICE_BUS_CONNECTION_STRING="Endpoint=sb://..."        # shared-access key

# 2. Start the worker
python -m backend.worker
```

The worker exposes its own health endpoints on `WORKER_HEALTH_PORT` (default `8001`):

| Endpoint | Purpose |
|----------|---------|
| `GET /health/live` | Liveness — worker process is running |
| `GET /health/ready` | Readiness — DB reachable and Service Bus session active |

---

## Configuration Reference

All worker settings are loaded from environment variables (or `.env`).

### `AppSettings`

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKFLOW_EXECUTOR` | `in_process` | `in_process` or `azure_service_bus` |

### `ServiceBusSettings` *(azure_service_bus mode only)*

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_SERVICE_BUS_NAMESPACE` | — | Fully qualified namespace (e.g. `mybus.servicebus.windows.net`). Takes precedence over `AZURE_SERVICE_BUS_CONNECTION_STRING`. Used with `DefaultAzureCredential` (managed identity / CLI login). |
| `AZURE_SERVICE_BUS_CONNECTION_STRING` | — | Shared-access connection string. Used when namespace is not set. |
| `AZURE_SERVICE_BUS_QUEUE_NAME` | `workflow-jobs` | Queue name for `WorkflowJob` messages. |

### `WorkerSettings`

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_MAX_CONCURRENCY` | `3` | Maximum simultaneous pipeline executions (semaphore). |
| `WORKER_SHUTDOWN_TIMEOUT_SECONDS` | `300` | Seconds to wait for in-flight jobs to finish on SIGTERM/SIGINT. |
| `WORKER_HEALTH_PORT` | `8001` | Port for the worker's HTTP health endpoints. |

### `EventSettings`

| Variable | Default | Description |
|----------|---------|-------------|
| `EVENT_CHANNEL_NAME` | `workflow_events` | PostgreSQL `NOTIFY` channel used by the worker to push events to the API. |

---

## Container Deployment

The worker is built from its own dedicated container image (`deploy/worker.Dockerfile`). In `podman-compose.yml` it is started as a separate service with `WORKFLOW_EXECUTOR=azure_service_bus` and the appropriate Service Bus credentials.

```bash
# Build and run all services (frontend + api + worker)
podman-compose up --build
```

To run only the worker container:

```bash
podman build -f deploy/worker.Dockerfile -t marketing-worker:local .
podman run --env-file .env \
  -e WORKFLOW_EXECUTOR=azure_service_bus \
  marketing-worker:local
```

---

## Job Actions

The worker handles three job actions, dispatched by the API or by the worker itself on retry:

| Action | Trigger | Description |
|--------|---------|-------------|
| `start_pipeline` | POST `/api/campaigns` | Starts a new agent pipeline from the campaign brief. |
| `resume_pipeline` | POST `/api/campaigns/{id}/clarify` or `/content-approve` | Resumes a pipeline paused at a human-in-the-loop gate. |
| `retry_stage` | Internal / manual re-queue | Retries a specific pipeline stage after a transient failure. |

---

## Observability

The worker emits OpenTelemetry spans and uses Python's `logging` module at `APP_LOG_LEVEL` (default `INFO`). Configure tracing with the same `TracingSettings` variables used by the API:

```bash
TRACING_ENABLED=true
TRACING_EXPORTER=otlp          # console | otlp | azure_monitor
OTLP_ENDPOINT=http://localhost:4317
```

---

## Related Documentation

- [Backend README](README.md) — API runbook and agent pipeline description
- [Root README](../README.md) — Architecture overview and quick start
- [Planning doc](../docs/planning/backend-split/ISSUE-007-docs-and-local-runbooks.md)
