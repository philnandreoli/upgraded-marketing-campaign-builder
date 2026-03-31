---
applyTo: "backend/**/*.py"
---

# Backend API Development Instructions

This project uses **FastAPI** with async SQLAlchemy, Pydantic v2, and a Store/Service layered architecture.

---

## Routers & Endpoints

- Create routers with `APIRouter(tags=[...])`. Register them on the app in `main.py`.
- Always declare `response_model=` and an explicit `status_code=` on every endpoint decorator.
  - POST that creates a resource → `status_code=201`
  - All other methods → `status_code=200` (or appropriate 2xx)
- Apply rate limiting with `@limiter.limit("N/minute")` directly above `async def`, below the route decorator.
- Endpoint functions must be `async def`.

```python
@router.post("/campaigns", status_code=201, response_model=CreateCampaignResponse)
@limiter.limit("10/minute")
async def create_campaign(
    workspace_id: str,
    request: Request,
    body: CreateCampaignRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> CreateCampaignResponse:
    ...
```

---

## Schemas (Pydantic DTOs)

- Keep domain models in `backend/models/`. Keep API-specific request/response models in `backend/apps/api/schemas/`.
- Request models end with `Request`. Response models end with `Response`.
- PATCH request bodies must have **all fields `Optional`** (partial update).
- Never expose raw ORM objects in responses — always return a typed Pydantic model.
- Return Pydantic model instances directly from route functions; FastAPI handles serialization.

```python
# Partial update body
class UpdateDraftRequest(BaseModel):
    product_or_service: Optional[str] = None
    goal: Optional[str] = None
```

---

## Dependency Injection

- Use `Depends()` for anything reusable: auth, stores, RBAC-gated resource loading.
- Prefer dedicated RBAC dependencies (`get_campaign_for_read`, `get_campaign_for_write`) over inline access checks inside route handlers.
- Stores and services are accessed via factory functions (`get_campaign_store()`, `get_workflow_service()`), not direct instantiation.

```python
@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign: Campaign = Depends(get_campaign_for_read),
) -> CampaignResponse:
    ...
```

---

## Error Handling

- Domain/service-layer exceptions (e.g., `WorkflowConflictError`, `ConcurrentUpdateError`) must **not** leak into HTTP responses. Catch them in the API layer and convert to `HTTPException`.
- Standard HTTP error mapping:
  - `400` — validation failure (business rule, not Pydantic)
  - `401` — missing or invalid authentication
  - `403` — authenticated but insufficient permissions
  - `404` — resource not found (or RBAC denies existence)
  - `409` — state conflict (workflow violation, concurrent update)
  - `422` — Pydantic validation error (automatic)
- For RBAC denials that reveal resource existence, prefer `404` over `403`.

```python
try:
    await workflow.submit_clarification(campaign.id, response)
except WorkflowConflictError as exc:
    raise HTTPException(status_code=409, detail=str(exc))
except ValueError:
    raise HTTPException(status_code=404, detail="Campaign not found")
```

---

## Authentication & RBAC

- Inject the current user with `user: Optional[User] = Depends(get_current_user)`.
- `get_current_user` returns `None` when `AUTH_ENABLED=False` — all auth-aware code must handle `None`.
- Never hard-code authorization logic inside route handlers. Use or extend the `_authorize()` helper in `dependencies.py`.
- RBAC action matrix: admins bypass all checks; builders are restricted by campaign/workspace membership role (OWNER > EDITOR > VIEWER).

---

## Database / Async

- The database is **PostgreSQL**. Use PostgreSQL-compatible SQL and avoid syntax specific to other engines.
- All DB interactions go through the **Store** layer, never directly inside route handlers.
- Stores use `async_session()` internally; do not pass sessions from the API layer.
- Always `await` store and service calls.

---

## Code Clarity & Documentation

- Every public function, method, and class must have a docstring that describes **what it does**, not how.
  - Route handlers: describe the HTTP operation and any notable side effects.
  - Store/service methods: describe parameters, return value, and exceptions that may be raised.
  - Dependencies: describe what they resolve and any access control they enforce.
- Use clear, descriptive names for variables and functions. Avoid abbreviations unless they are well-known in context (e.g., `id`, `url`).
- Keep functions focused on a single responsibility. If a function needs a long comment to explain its internal steps, break it into smaller functions.
- Prefer explicit over implicit — avoid clever one-liners when a readable multi-line form is clearer.

```python
async def get_campaign_for_write(
    workspace_id: str,
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Campaign:
    """FastAPI dependency: load a campaign and authorize WRITE access.

    Raises:
        HTTPException 404: if the campaign does not exist or belongs to a different workspace.
        HTTPException 403: if the user lacks write permission.
    """
    ...
```

---

## Layering Rules

| Layer | Responsibility | May call |
|---|---|---|
| `api/` | HTTP in/out, auth, rate limiting | `application/`, `infrastructure/` stores |
| `application/` | Business logic, orchestration | `infrastructure/` stores |
| `infrastructure/` | Persistence, external services | DB, external APIs |
| `models/` | Domain data structures | nothing |

- Never import from `api/` in `application/` or `infrastructure/`.
- Never put business logic directly in route handlers — delegate to a service.
