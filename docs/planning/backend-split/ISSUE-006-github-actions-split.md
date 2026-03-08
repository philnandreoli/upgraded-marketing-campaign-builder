# ISSUE-006 — Split GitHub Actions for API, Workflow Engine, and Shared Checks

**Epic:** philnandreoli/upgraded-marketing-campaign-builder#185

## Problem

`.github/workflows/ci.yml` treated the backend as one artifact and one validation surface.
Any change to any backend file — whether API-only, worker-only, or shared — triggered a single
monolithic CI job that built one generic backend image.  This prevented path-based build
optimisation and made it impossible to enforce separate deployment gates for the two runtime
processes.

## Proposal

Replace the single broad CI workflow with four targeted workflow files:

| File | Purpose |
|------|---------|
| `.github/workflows/backend-api.yml` | API-focused tests + API image build |
| `.github/workflows/backend-worker.yml` | Worker-focused tests + worker image build |
| `.github/workflows/backend-shared.yml` | Cross-cutting quality gate (shared paths) |
| `.github/workflows/frontend.yml` | Frontend lint, build, and image |

## Path Boundaries

### API-specific paths
```
backend/apps/api/**
backend/api/**
backend/main.py
```

### Worker-specific paths
```
backend/worker.py
backend/__main__.py
backend/orchestration/**
backend/agents/**
```

### Shared backend paths (trigger both API and worker pipelines)
```
backend/core/**
backend/infrastructure/**
backend/application/**
backend/models/**
backend/services/**
backend/config.py
backend/migrations/**
requirements.txt
```

### Frontend paths
```
frontend/**
```

## Trigger Matrix

| Changed path | `backend-api` | `backend-worker` | `backend-shared` | `frontend` |
|---|---|---|---|---|
| `backend/apps/api/**` | ✅ | — | — | — |
| `backend/worker.py` | — | ✅ | — | — |
| `backend/core/**` | ✅ | ✅ | ✅ | — |
| `frontend/**` | — | — | — | ✅ |

## Container Artifacts

Two separate Dockerfiles are introduced under `deploy/`:

| File | Image tag | Entry-point |
|------|-----------|-------------|
| `deploy/api.Dockerfile` | `marketing-api:ci` | `uvicorn backend.apps.api.main:app` |
| `deploy/worker.Dockerfile` | `marketing-worker:ci` | `python -m backend.worker` |

## Acceptance Criteria

- [x] Changes under API-only paths do not trigger the worker image build.
- [x] Changes under worker-only paths do not trigger the API image build.
- [x] Changes under shared backend paths trigger both pipelines.
- [x] Frontend workflow remains independent of all backend workflows.
- [x] `deploy/api.Dockerfile` builds successfully with `docker build -f deploy/api.Dockerfile -t marketing-api:ci .`
- [x] `deploy/worker.Dockerfile` builds successfully with `docker build -f deploy/worker.Dockerfile -t marketing-worker:ci .`

## Local Validation Commands

```bash
# Run all backend tests
AZURE_AI_PROJECT_ENDPOINT=https://placeholder.example.com pytest

# Build API image
docker build -f deploy/api.Dockerfile -t marketing-api:ci .

# Build worker image
docker build -f deploy/worker.Dockerfile -t marketing-worker:ci .

# Frontend
cd frontend && npm ci && npm run lint && npm run build
```

## References

- [Backend/API runbook](../../backend/README.md)
- [Workflow-engine runbook](../../backend/WORKFLOW_ENGINE.md)
- [Frontend runbook](../../frontend/README.md)
- [ISSUE-007 docs and runbooks](./ISSUE-007-docs-and-local-runbooks.md)
