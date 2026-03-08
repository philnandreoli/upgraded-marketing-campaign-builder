# ISSUE-007 — Docs and Local Runbooks for Split Backend Model

**Epic:** philnandreoli/upgraded-marketing-campaign-builder#185

## Problem

The current docs do not fully describe the target split backend model, the future container artifacts, or the runtime-specific local development story.

## Proposal

Refresh project documentation to describe the split backend model, local development commands, deployment artifacts, and final workflow names.

## Scope

| Deliverable | File | Status |
|-------------|------|--------|
| Root architecture and local run overview | `README.md` | ✅ Updated |
| API runbook | `backend/README.md` | ✅ Updated |
| Workflow-engine runbook | `backend/WORKFLOW_ENGINE.md` | ✅ Created |
| Frontend runbook | `frontend/README.md` | ✅ Updated |
| Planning doc | `docs/planning/backend-split/ISSUE-007-docs-and-local-runbooks.md` | ✅ This file |

## Acceptance Criteria

- [x] A new contributor can run the API locally in in-process mode.
- [x] A developer can run the frontend locally against the API.
- [x] An operator can run the workflow engine locally once queue credentials are available.
- [x] Documentation aligns with the final entrypoints, container files, and GitHub Actions workflow names.

## Local Validation Commands

### API (in-process mode — no Service Bus needed)

```bash
pip install -r requirements.txt
uvicorn backend.apps.api.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend && npm install && npm run dev -- --host 0.0.0.0 --port 5173
```

### Workflow engine (requires Service Bus credentials)

```bash
export WORKFLOW_EXECUTOR=azure_service_bus
python -m backend.worker
```

## Key Architecture Decisions Documented

### Split Backend Model

The backend is split into two independent runtime processes:

1. **API process** (`backend.apps.api.main:app`) — HTTP/WebSocket, enqueues jobs
2. **Worker process** (`python -m backend.worker`) — runs the agent pipeline

For local development these collapse into one: `WORKFLOW_EXECUTOR=in_process` (default).

### Canonical Entry-Point

The canonical FastAPI entry-point is `backend.apps.api.main:app`. The legacy `backend.main:app` shim continues to work for backward compatibility.

### Container Artifacts

| Artifact | Path | CMD |
|----------|------|-----|
| API image | `deploy/api.Dockerfile` | `uvicorn backend.apps.api.main:app --host 0.0.0.0 --port 8000` |
| Worker image | `deploy/worker.Dockerfile` | `python -m backend.worker` |
| Frontend image | `frontend/Containerfile` | nginx serving the Vite build |

### CI Workflows

The monolithic `.github/workflows/ci.yml` has been replaced by four path-filtered workflows:

| File | Trigger paths | Jobs |
|------|--------------|------|
| `.github/workflows/backend-api.yml` | API + shared backend paths | `backend-tests`, `build-api-image` |
| `.github/workflows/backend-worker.yml` | Worker + shared backend paths | `backend-tests`, `build-worker-image` |
| `.github/workflows/backend-shared.yml` | Shared backend paths only | `shared-quality` |
| `.github/workflows/frontend.yml` | `frontend/**` | `frontend-lint-build`, `build-frontend-image` |

## References

- [Root README](../../README.md)
- [Backend/API runbook](../../backend/README.md)
- [Workflow-engine runbook](../../backend/WORKFLOW_ENGINE.md)
- [Frontend runbook](../../frontend/README.md)
