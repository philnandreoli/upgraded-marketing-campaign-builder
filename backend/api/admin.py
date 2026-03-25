"""
Admin REST API routes.

Endpoints:
  GET    /api/admin/users                        — List all users (search by name/email)
  GET    /api/admin/users/{user_id}              — Get a single user with campaign memberships
  PATCH  /api/admin/users/{user_id}/role         — Change a user's platform role
  DELETE /api/admin/users/{user_id}              — Deactivate a user (soft delete)
  POST   /api/admin/users/{user_id}/reactivate   — Reactivate an inactive user
  GET    /api/admin/campaigns                    — List all campaigns (admin view)
  GET    /api/admin/entra/users                  — Search Microsoft Entra ID directory
  POST   /api/admin/users                        — Pre-provision a user from Entra ID
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from backend.config import get_settings
from backend.models.user import User, UserRole, roles_from_db, roles_to_db
from backend.infrastructure.auth import require_admin
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.database import CampaignMemberRow, UserRow, WorkspaceMemberRow, WorkspaceRow, get_db
from backend.infrastructure.graph import InvalidSearchInputError, search_entra_users
from backend.core.rate_limit import limiter

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class RoleUpdateRequest(BaseModel):
    roles: list[str]


class ProvisionUserRequest(BaseModel):
    entra_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    roles: list[str] = ["viewer"]


class EntraUserResult(BaseModel):
    id: str
    display_name: Optional[str] = None
    mail: Optional[str] = None
    user_principal_name: Optional[str] = None


class UserListResponse(BaseModel):
    id: str
    email: Optional[str]
    display_name: Optional[str]
    roles: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    workspace_count: int = 0


class UserDetailResponse(BaseModel):
    id: str
    email: Optional[str]
    display_name: Optional[str]
    roles: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    campaign_memberships: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserListResponse])
@limiter.limit("120/minute")
async def list_users(
    request: Request,
    response: Response,
    search: Optional[str] = Query(default=None, description="Filter by name or email"),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=25, ge=1, le=200, description="Number of results per page"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserListResponse]:
    """List all platform users, optionally filtered by name/email with pagination."""
    base = (
        select(
            UserRow,
            func.count(WorkspaceMemberRow.workspace_id).label("ws_count"),
        )
        .outerjoin(WorkspaceMemberRow, UserRow.id == WorkspaceMemberRow.user_id)
        .group_by(UserRow.id)
    )

    if search:
        term = f"%{search}%"
        base = base.where(
            or_(
                UserRow.email.ilike(term),
                UserRow.display_name.ilike(term),
            )
        )

    # Total count (uses same filter, no ordering needed).
    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    # Paginated data query.
    stmt = base.order_by(UserRow.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).all()

    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)

    return [
        UserListResponse(
            id=r.UserRow.id,
            email=r.UserRow.email,
            display_name=r.UserRow.display_name,
            roles=[v.strip() for v in r.UserRow.role.split(",") if v.strip()],
            is_active=r.UserRow.is_active,
            created_at=r.UserRow.created_at,
            updated_at=r.UserRow.updated_at,
            workspace_count=r.ws_count,
        )
        for r in rows
    ]


@router.get("/users/{user_id}", response_model=UserDetailResponse)
@limiter.limit("30/minute")
async def get_user(
    request: Request,
    response: Response,
    user_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserDetailResponse:
    """Get a single user's details including campaign memberships."""
    row = await db.get(UserRow, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    memberships_result = await db.execute(
        select(CampaignMemberRow).where(CampaignMemberRow.user_id == user_id)
    )
    memberships = memberships_result.scalars().all()

    return UserDetailResponse(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        roles=[v.strip() for v in row.role.split(",") if v.strip()],
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        campaign_memberships=[
            {
                "campaign_id": m.campaign_id,
                "role": m.role,
                "added_at": m.added_at.isoformat(),
            }
            for m in memberships
        ],
    )


@router.patch("/users/{user_id}/role", response_model=UserListResponse)
@limiter.limit("30/minute")
async def update_user_role(
    request: Request,
    response: Response,
    user_id: str,
    body: RoleUpdateRequest = Body(),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """Change a user's platform roles. Prevents removing the last admin."""
    # Validate each role string
    try:
        new_roles = [UserRole(r) for r in body.roles]
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid role(s): {body.roles!r}")

    if not new_roles:
        raise HTTPException(status_code=422, detail="At least one role is required.")

    if UserRole.CAMPAIGN_BUILDER in new_roles and UserRole.VIEWER in new_roles:
        raise HTTPException(
            status_code=422,
            detail="A user cannot be both a campaign_builder and a viewer.",
        )

    row = await db.get(UserRow, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Guard: when removing admin, ensure at least one other active admin remains.
    current_roles = [v.strip() for v in row.role.split(",") if v.strip()]
    was_admin = UserRole.ADMIN.value in current_roles
    will_be_admin = UserRole.ADMIN in new_roles
    if was_admin and not will_be_admin:
        count_result = await db.execute(
            select(func.count())
            .select_from(UserRow)
            .where(UserRow.role.contains(UserRole.ADMIN.value), UserRow.is_active == True)  # noqa: E712
        )
        admin_count = count_result.scalar_one()
        if admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="Cannot remove the last admin. Assign another admin first.",
            )

    row.role = roles_to_db(new_roles)
    row.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(row)

    return UserListResponse(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        roles=[v.strip() for v in row.role.split(",") if v.strip()],
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/users/{user_id}", status_code=204)
@limiter.limit("30/minute")
async def deactivate_user(
    request: Request,
    response: Response,
    user_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a user: set is_active=False and remove all campaign memberships."""
    row = await db.get(UserRow, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    row.is_active = False
    row.updated_at = datetime.utcnow()

    await db.execute(
        sa_delete(CampaignMemberRow).where(CampaignMemberRow.user_id == user_id)
    )
    await db.commit()

    return Response(status_code=204)


@router.post("/users/{user_id}/reactivate", response_model=UserListResponse)
@limiter.limit("30/minute")
async def reactivate_user(
    request: Request,
    response: Response,
    user_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """Reactivate an inactive user: set is_active=True."""
    row = await db.get(UserRow, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    if row.is_active:
        raise HTTPException(status_code=409, detail="User is already active")

    row.is_active = True
    row.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(row)

    return UserListResponse(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        roles=[v.strip() for v in row.role.split(",") if v.strip()],
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/entra/users", response_model=list[EntraUserResult])
@limiter.limit("120/minute")
async def search_entra_directory(
    request: Request,
    response: Response,
    search: str = Query(description="Name or email prefix to search for in Entra ID"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[EntraUserResult]:
    """Search Microsoft Entra ID for users matching the given name/email prefix.

    Returns matching directory users that have NOT yet been provisioned in the
    local database. Requires ``AZURE_CLIENT_SECRET`` to be configured.
    """
    settings = get_settings()

    if not settings.oidc.graph_client_secret:
        raise HTTPException(
            status_code=501,
            detail=(
                "Entra ID directory search is not configured. "
                "Set AZURE_CLIENT_SECRET, OIDC_AUTHORITY, and OIDC_CLIENT_ID "
                "to enable this feature."
            ),
        )

    if not search or not search.strip():
        return []

    try:
        entra_users = await search_entra_users(
            search=search.strip(),
            authority=settings.oidc.authority,
            client_id=settings.oidc.client_id,
            client_secret=settings.oidc.graph_client_secret,
        )
    except InvalidSearchInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Graph API search failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to query the Entra ID directory. Check the server logs for details.",
        ) from exc

    if not entra_users:
        return []

    # Exclude users that are already provisioned in the local database.
    entra_ids = [u["id"] for u in entra_users]
    result = await db.execute(select(UserRow.id).where(UserRow.id.in_(entra_ids)))
    existing_ids = {row for (row,) in result.all()}

    return [
        EntraUserResult(
            id=u["id"],
            display_name=u.get("displayName"),
            mail=u.get("mail"),
            user_principal_name=u.get("userPrincipalName"),
        )
        for u in entra_users
        if u["id"] not in existing_ids
    ]


@router.post("/users", response_model=UserListResponse, status_code=201)
@limiter.limit("30/minute")
async def provision_user(
    request: Request,
    response: Response,
    body: ProvisionUserRequest = Body(),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """Pre-provision a user from Entra ID with the specified roles.

    Creates a ``UserRow`` using the Entra object ID so that the JIT
    provisioning flow (``_provision_user`` in auth.py) will find the
    pre-created record on the user's first login.
    """
    # Validate roles
    try:
        new_roles = [UserRole(r) for r in body.roles]
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid role(s): {body.roles!r}")

    if not new_roles:
        raise HTTPException(status_code=422, detail="At least one role is required.")

    if UserRole.CAMPAIGN_BUILDER in new_roles and UserRole.VIEWER in new_roles:
        raise HTTPException(
            status_code=422,
            detail="A user cannot be both a campaign_builder and a viewer.",
        )

    # Check for duplicate
    existing = await db.get(UserRow, body.entra_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"A user with id '{body.entra_id}' already exists in the platform.",
        )

    now = datetime.utcnow()
    row = UserRow(
        id=body.entra_id,
        email=body.email,
        display_name=body.display_name,
        role=roles_to_db(new_roles),
        created_at=now,
        updated_at=now,
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    return UserListResponse(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        roles=[v.strip() for v in row.role.split(",") if v.strip()],
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/campaigns")
@limiter.limit("30/minute")
async def list_all_campaigns(
    request: Request,
    response: Response,
    _: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List all campaigns across all users (admin view)."""
    store = get_campaign_store()
    campaigns = await store.list_all()

    # Resolve workspace info in a single batch (one lookup per unique workspace_id)
    unique_ws_ids = {c.workspace_id for c in campaigns if c.workspace_id is not None}
    ws_map: dict[str, Any] = {}
    if unique_ws_ids:
        results = await asyncio.gather(
            *[store.get_workspace(ws_id) for ws_id in unique_ws_ids],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Failed to look up workspace: %s", result)
            elif result is not None:
                ws_map[result.id] = {"id": result.id, "name": result.name, "is_personal": result.is_personal}

    return [
        {
            "id": c.id,
            "status": c.status.value,
            "product_or_service": c.brief.product_or_service,
            "goal": c.brief.goal,
            "owner_id": c.owner_id,
            "workspace_id": c.workspace_id,
            "workspace": ws_map.get(c.workspace_id) if c.workspace_id else None,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in campaigns
    ]


# ---------------------------------------------------------------------------
# User workspace access
# ---------------------------------------------------------------------------


class UserWorkspaceDetail(BaseModel):
    workspace_id: str
    workspace_name: str
    is_personal: bool
    role: str
    added_at: datetime


@router.get("/users/{user_id}/workspaces", response_model=list[UserWorkspaceDetail])
@limiter.limit("30/minute")
async def get_user_workspaces(
    request: Request,
    response: Response,
    user_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserWorkspaceDetail]:
    """Get all workspaces a user has access to, with their role in each."""
    row = await db.get(UserRow, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = (
        select(WorkspaceMemberRow, WorkspaceRow)
        .join(WorkspaceRow, WorkspaceMemberRow.workspace_id == WorkspaceRow.id)
        .where(WorkspaceMemberRow.user_id == user_id)
        .order_by(WorkspaceMemberRow.added_at.desc())
    )
    results = (await db.execute(stmt)).all()

    return [
        UserWorkspaceDetail(
            workspace_id=r.WorkspaceRow.id,
            workspace_name=r.WorkspaceRow.name,
            is_personal=r.WorkspaceRow.is_personal,
            role=r.WorkspaceMemberRow.role,
            added_at=r.WorkspaceMemberRow.added_at,
        )
        for r in results
    ]
