"""
Campaign member management routes.

Endpoints:
  GET    /api/campaigns/{id}/members            — List all campaign members
  POST   /api/campaigns/{id}/members            — Add a member
  PATCH  /api/campaigns/{id}/members/{user_id}  — Change a member's role
  DELETE /api/campaigns/{id}/members/{user_id}  — Remove a member
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend.models.campaign import Campaign
from backend.models.user import CampaignMemberRole, User
from backend.services.auth import get_current_user
from backend.api.websocket import manager as ws_manager

# Access get_campaign_store through the campaigns module so that test patches on
# backend.api.campaigns.get_campaign_store continue to work without modification.
import backend.api.campaigns as _cam

from backend.api.campaigns import (
    Action,
    _authorize,
    AddMemberRequest,
    UpdateMemberRoleRequest,
    CampaignMemberResponse,
    get_campaign_for_read,
)

router = APIRouter(tags=["campaigns"])


@router.get("/campaigns/{campaign_id}/members")
async def list_campaign_members(
    campaign: Campaign = Depends(get_campaign_for_read),
) -> list[CampaignMemberResponse]:
    """List all members of a campaign. Requires READ access."""
    store = _cam.get_campaign_store()
    members = await store.list_members(campaign.id)
    return [
        CampaignMemberResponse(
            campaign_id=m.campaign_id,
            user_id=m.user_id,
            role=m.role.value,
            added_at=m.added_at,
        )
        for m in members
    ]


@router.post("/campaigns/{campaign_id}/members", status_code=201)
async def add_campaign_member(
    campaign_id: str,
    body: AddMemberRequest,
    user: Optional[User] = Depends(get_current_user),
) -> CampaignMemberResponse:
    """Add a member to a campaign. Requires MANAGE_MEMBERS access (owner or admin)."""
    store = _cam.get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.MANAGE_MEMBERS, store)

    target_user = await store.get_user(body.user_id)
    if target_user is None or not target_user.is_active:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    role = CampaignMemberRole(body.role)
    await store.add_member(campaign_id, body.user_id, role)

    await ws_manager.broadcast({
        "event": "member_added",
        "campaign_id": campaign_id,
        "user_id": body.user_id,
        "role": body.role,
    })

    return CampaignMemberResponse(
        campaign_id=campaign_id,
        user_id=body.user_id,
        role=body.role,
        added_at=datetime.utcnow(),
    )


@router.patch("/campaigns/{campaign_id}/members/{target_user_id}")
async def update_campaign_member_role(
    campaign_id: str,
    target_user_id: str,
    body: UpdateMemberRoleRequest,
    user: Optional[User] = Depends(get_current_user),
) -> CampaignMemberResponse:
    """Change a member's campaign role. Requires MANAGE_MEMBERS access."""
    store = _cam.get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.MANAGE_MEMBERS, store)

    target_user = await store.get_user(target_user_id)
    if target_user is None or not target_user.is_active:
        raise HTTPException(status_code=404, detail="User not found or inactive")

    existing_member = await store.get_member(campaign_id, target_user_id)
    if existing_member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    role = CampaignMemberRole(body.role)
    await store.add_member(campaign_id, target_user_id, role)

    return CampaignMemberResponse(
        campaign_id=campaign_id,
        user_id=target_user_id,
        role=body.role,
        added_at=existing_member.added_at,
    )


@router.delete("/campaigns/{campaign_id}/members/{target_user_id}")
async def remove_campaign_member(
    campaign_id: str,
    target_user_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    """Remove a member from a campaign. Requires MANAGE_MEMBERS access.
    Prevents removing the last owner."""
    store = _cam.get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await _authorize(campaign_id, user, Action.MANAGE_MEMBERS, store)

    members = await store.list_members(campaign_id)
    member = next((m for m in members if m.user_id == target_user_id), None)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    owner_count = sum(1 for m in members if m.role == CampaignMemberRole.OWNER)
    if member.role == CampaignMemberRole.OWNER and owner_count <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last owner")

    await store.remove_member(campaign_id, target_user_id)

    await ws_manager.broadcast({
        "event": "member_removed",
        "campaign_id": campaign_id,
        "user_id": target_user_id,
    })

    return Response(status_code=204)
