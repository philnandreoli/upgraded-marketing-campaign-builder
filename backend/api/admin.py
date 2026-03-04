"""
Admin REST API routes.

Endpoints:
  GET    /api/admin/users                — List all users (search by name/email)
  GET    /api/admin/users/{user_id}      — Get a single user with campaign memberships
  PATCH  /api/admin/users/{user_id}/role — Change a user's platform role
  DELETE /api/admin/users/{user_id}      — Deactivate a user (soft delete)
  GET    /api/admin/campaigns            — List all campaigns (admin view)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User, UserRole, roles_from_db, roles_to_db
from backend.services.auth import require_admin
from backend.services.campaign_store import get_campaign_store
from backend.services.database import CampaignMemberRow, UserRow, get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class RoleUpdateRequest(BaseModel):
    roles: list[str]


class UserListResponse(BaseModel):
    id: str
    email: Optional[str]
    display_name: Optional[str]
    roles: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


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
async def list_users(
    search: Optional[str] = Query(default=None, description="Filter by name or email"),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserListResponse]:
    """List all platform users, optionally filtered by name/email."""
    result = await db.execute(select(UserRow).order_by(UserRow.created_at.desc()))
    rows = result.scalars().all()

    if search:
        term = search.lower()
        rows = [
            r for r in rows
            if (r.email and term in r.email.lower())
            or (r.display_name and term in r.display_name.lower())
        ]

    return [
        UserListResponse(
            id=r.id,
            email=r.email,
            display_name=r.display_name,
            roles=[v.strip() for v in r.role.split(",") if v.strip()],
            is_active=r.is_active,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
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
async def update_user_role(
    user_id: str,
    body: RoleUpdateRequest,
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
async def deactivate_user(
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


@router.get("/campaigns")
async def list_all_campaigns(
    _: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List all campaigns across all users (admin view)."""
    store = get_campaign_store()
    campaigns = await store.list_all()
    return [
        {
            "id": c.id,
            "status": c.status.value,
            "product_or_service": c.brief.product_or_service,
            "goal": c.brief.goal,
            "owner_id": c.owner_id,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in campaigns
    ]
