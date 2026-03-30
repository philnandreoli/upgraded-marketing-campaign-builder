"""
Workspace REST API — CRUD routes.

Endpoints:
  POST   /api/workspaces                        — Create a workspace
  GET    /api/workspaces                        — List workspaces the user belongs to
  GET    /api/workspaces/{id}                   — Get workspace details
  PATCH  /api/workspaces/{id}                   — Update workspace name/description
  DELETE /api/workspaces/{id}                   — Delete workspace

Membership routes live in workspace_members.py.
Campaign routes live in campaigns.py (mounted under /api/workspaces/{id}).
Shared RBAC helpers (_authorize_workspace, WorkspaceAction) and Pydantic DTOs are
defined here and imported by workspace_members.py and campaigns.py.
"""

from __future__ import annotations

import calendar
import json as _json
from collections import defaultdict
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from backend.apps.api.schemas.common import PaginationMeta
from backend.apps.api.schemas.schedule import (
    WorkspaceCalendarDayGroup,
    WorkspaceCalendarPiece,
    WorkspaceCalendarResponse,
)
from backend.models.user import User, UserRole
from backend.models.workspace import Workspace, WorkspaceRole
from backend.models.campaign import ContentPiece
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store

router = APIRouter(tags=["workspaces"])


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------

class WorkspaceAction(str, Enum):
    """Actions that can be performed on a workspace, used in authorization checks."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    MANAGE_MEMBERS = "manage_members"


async def _authorize_workspace(
    workspace_id: str,
    user: Optional[User],
    action: WorkspaceAction,
    store: Any,
) -> None:
    """Enforce RBAC for workspace access.

    Authorization matrix:
      Platform Role | Workspace Role | READ | WRITE | DELETE | MANAGE_MEMBERS
      admin         | (any/none)     |  ✅  |  ✅   |  ✅    |  ✅
      any           | CREATOR        |  ✅  |  ✅   |  ✅    |  ✅
      any           | CONTRIBUTOR    |  ✅  |  ❌   |  ❌    |  ❌
      any           | VIEWER         |  ✅  |  ❌   |  ❌    |  ❌
      any           | (none)         |  ❌  |  ❌   |  ❌    |  ❌

    When auth is disabled (user is None) all workspaces are accessible.
    Raises 404 when the user has no membership (to avoid leaking workspace existence).
    Raises 403 when authenticated but the action exceeds the user's permission.
    """
    if user is None:
        return  # auth disabled — allow everything

    if user.is_admin:
        return  # admins have full access

    role = await store.get_workspace_member_role(workspace_id, user.id)
    if role is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if role == WorkspaceRole.CREATOR:
        allowed = True
    else:
        # CONTRIBUTOR and VIEWER get READ-only workspace access
        allowed = action == WorkspaceAction.READ

    if not allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


# ---------------------------------------------------------------------------
# Request / Response DTOs
# ---------------------------------------------------------------------------

class CreateWorkspaceRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateWorkspaceRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    owner_id: str
    is_personal: bool
    created_at: datetime
    updated_at: datetime


class WorkspaceSummary(BaseModel):
    id: str
    name: str
    is_personal: bool
    role: str  # the current user's role in this workspace
    member_count: int = 0
    campaign_count: int = 0
    owner_id: Optional[str] = None
    owner_display_name: Optional[str] = None
    created_at: Optional[datetime] = None
    draft_count: int = 0
    in_progress_count: int = 0
    awaiting_approval_count: int = 0
    approved_count: int = 0


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceSummary]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/workspaces", status_code=201, response_model=WorkspaceResponse)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceResponse:
    """Create a workspace. Requires campaign_builder or admin role.
    The creator is automatically added as a CREATOR member."""
    if user is not None and user.is_viewer and not user.is_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    store = get_campaign_store()
    owner_id = user.id if user is not None else "local"
    workspace = await store.create_workspace(
        name=body.name,
        owner_id=owner_id,
        description=body.description,
    )
    return _workspace_to_response(workspace)


@router.get("/workspaces", response_model=list[WorkspaceSummary] | WorkspaceListResponse)
async def list_workspaces(
    response: Response,
    user: Optional[User] = Depends(get_current_user),
    limit: Optional[int] = Query(default=None, ge=1, description="Optional max number of workspaces to return."),
    offset: int = Query(default=0, ge=0, description="Optional number of workspaces to skip before returning results."),
    pagination_format: Literal["legacy", "meta"] = Query(
        default="legacy",
        description="Response contract format. Use 'meta' for standardized {items, pagination} envelope.",
    ),
) -> list[WorkspaceSummary] | WorkspaceListResponse:
    """List workspaces the current user belongs to. Admins see all workspaces."""
    store = get_campaign_store()
    if user is not None:
        workspaces = await store.list_workspaces(user.id, is_admin=user.is_admin)
    else:
        workspaces = await store.list_workspaces("local", is_admin=True)

    summary_map: dict[str, dict[str, Any]] = {}
    workspace_ids = [ws.id for ws in workspaces]
    if hasattr(store, "get_workspace_summaries"):
        summary_map = await store.get_workspace_summaries(
            workspace_ids,
            user_id=user.id if user is not None else None,
            is_admin=user.is_admin if user is not None else True,
        )

    result: list[WorkspaceSummary] = []
    for ws in workspaces:
        summary = summary_map.get(ws.id)
        if summary is not None:
            role_str = str(summary.get("role", WorkspaceRole.VIEWER.value))
            member_count = int(summary.get("member_count", 0))
            campaign_count = int(summary.get("campaign_count", 0))
            owner_display_name = summary.get("owner_display_name")
            draft_count = int(summary.get("draft_count", 0))
            in_progress_count = int(summary.get("in_progress_count", 0))
            awaiting_approval_count = int(summary.get("awaiting_approval_count", 0))
            approved_count = int(summary.get("approved_count", 0))
        else:
            if user is not None:
                role = await store.get_workspace_member_role(ws.id, user.id)
                role_str = role.value if role is not None else WorkspaceRole.VIEWER.value
            else:
                role_str = WorkspaceRole.CREATOR.value
            # Use COUNT query when available to avoid loading full member list
            if hasattr(store, "count_workspace_members"):
                member_count = await store.count_workspace_members(ws.id)
            else:
                members = await store.list_workspace_members(ws.id)
                member_count = len(members)
            campaigns, campaign_count = await store.list_workspace_campaigns(ws.id)
            if ws.owner_id:
                owner_user = await store.get_user(ws.owner_id)
                owner_display_name = (
                    owner_user.display_name if owner_user is not None else None
                )
            else:
                owner_display_name = None
            draft_count = 0
            in_progress_count = 0
            awaiting_approval_count = 0
            approved_count = 0

        result.append(
            WorkspaceSummary(
                id=ws.id,
                name=ws.name,
                is_personal=ws.is_personal,
                role=role_str,
                member_count=member_count,
                campaign_count=campaign_count,
                owner_id=ws.owner_id,
                owner_display_name=owner_display_name,
                created_at=ws.created_at,
                draft_count=draft_count,
                in_progress_count=in_progress_count,
                awaiting_approval_count=awaiting_approval_count,
                approved_count=approved_count,
            )
        )
    total_count = len(result)
    end = offset + limit if limit is not None else None
    paged_result = result[offset:end]
    returned_count = len(paged_result)
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Offset"] = str(offset)
    response.headers["X-Limit"] = str(limit) if limit is not None else "all"
    response.headers["X-Returned-Count"] = str(returned_count)
    has_more = offset + returned_count < total_count
    response.headers["X-Has-More"] = str(has_more).lower()
    response.headers["X-Pagination-Format"] = "meta-v1"
    if pagination_format == "meta":
        return WorkspaceListResponse(
            items=paged_result,
            pagination=PaginationMeta(
                total_count=total_count,
                offset=offset,
                limit=limit,
                returned_count=returned_count,
                has_more=has_more,
            ),
        )
    return paged_result


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceResponse:
    """Get workspace details. Requires workspace membership or admin."""
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, store)
    return _workspace_to_response(workspace)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceResponse:
    """Update workspace name or description. Requires CREATOR role or admin."""
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.WRITE, store)
    try:
        updated = await store.update_workspace(
            workspace_id,
            name=body.name,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _workspace_to_response(updated)


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    """Delete a workspace. Personal workspaces cannot be deleted.
    Campaigns belonging to the workspace are orphaned (not deleted)."""
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.DELETE, store)
    if workspace.is_personal:
        raise HTTPException(status_code=409, detail="Personal workspaces cannot be deleted")
    await store.delete_workspace(workspace_id)
    return Response(status_code=204)


@router.get("/workspaces/{workspace_id}/calendar", response_model=WorkspaceCalendarResponse)
async def get_workspace_calendar(
    workspace_id: str,
    month: Optional[str] = Query(
        default=None,
        description="Month to filter by, in YYYY-MM format. Defaults to the current month.",
        pattern=r"^\d{4}-\d{2}$",
    ),
    user: Optional[User] = Depends(get_current_user),
) -> WorkspaceCalendarResponse:
    """Return all scheduled content pieces from every campaign in the workspace,
    grouped by date and annotated with campaign metadata.

    Requires workspace membership (any role) or platform admin.
    Only pieces whose ``scheduled_date`` falls within the requested month are included.
    """
    store = get_campaign_store()
    workspace = await store.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await _authorize_workspace(workspace_id, user, WorkspaceAction.READ, store)

    # Resolve the requested month boundaries
    today = datetime.now(timezone.utc).date()
    if month is not None:
        try:
            year, month_num = int(month[:4]), int(month[5:7])
            if not (1 <= month_num <= 12):
                raise ValueError("month out of range")
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Invalid month format; expected YYYY-MM")
    else:
        year, month_num = today.year, today.month

    _, days_in_month = calendar.monthrange(year, month_num)
    month_start = date(year, month_num, 1)
    month_end = date(year, month_num, days_in_month)

    # Collect calendar data for all campaigns in the workspace.
    # Prefer the dedicated calendar projection to avoid full JSON deserialization.
    scheduled_by_day: dict[date, list[WorkspaceCalendarPiece]] = defaultdict(list)

    if hasattr(store, "list_workspace_campaign_calendar_data"):
        calendar_rows = await store.list_workspace_campaign_calendar_data(workspace_id)
        for row in calendar_rows:
            content_json = row.get("content_json")
            if not content_json:
                continue
            campaign_name = row.get("campaign_name") or row["id"]
            try:
                content_data = _json.loads(content_json)
                pieces_data = content_data.get("pieces", [])
            except Exception:
                continue
            for idx, piece_data in enumerate(pieces_data):
                scheduled_date_raw = piece_data.get("scheduled_date")
                if not scheduled_date_raw:
                    continue
                try:
                    piece_date = date.fromisoformat(scheduled_date_raw)
                except (ValueError, TypeError):
                    continue
                if month_start <= piece_date <= month_end:
                    try:
                        piece = ContentPiece.model_validate(piece_data)
                    except Exception:
                        continue
                    scheduled_by_day[piece_date].append(
                        WorkspaceCalendarPiece(
                            campaign_id=row["id"],
                            campaign_name=campaign_name,
                            piece_index=idx,
                            piece=piece,
                        )
                    )
    else:
        # Fallback: full campaign deserialization (used by InMemoryCampaignStore in tests)
        campaigns, _total = await store.list_workspace_campaigns(
            workspace_id, include_drafts=True, limit=10_000, offset=0
        )
        for campaign in campaigns:
            if campaign.content is None:
                continue
            campaign_name = (
                campaign.brief.product_or_service
                if campaign.brief and campaign.brief.product_or_service
                else campaign.id
            )
            for idx, piece in enumerate(campaign.content.pieces):
                if piece.scheduled_date is None:
                    continue
                if month_start <= piece.scheduled_date <= month_end:
                    scheduled_by_day[piece.scheduled_date].append(
                        WorkspaceCalendarPiece(
                            campaign_id=campaign.id,
                            campaign_name=campaign_name,
                            piece_index=idx,
                            piece=piece,
                        )
                    )

    scheduled = [
        WorkspaceCalendarDayGroup(date=d, pieces=scheduled_by_day[d])
        for d in sorted(scheduled_by_day.keys())
    ]

    return WorkspaceCalendarResponse(scheduled=scheduled)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _workspace_to_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        owner_id=workspace.owner_id,
        is_personal=workspace.is_personal,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )
