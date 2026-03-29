"""Campaign clone and template-management routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.apps.api.dependencies import get_campaign_for_read, get_campaign_for_write
from backend.apps.api.schemas.campaigns import (
    CloneCampaignRequest,
    CreateCampaignResponse,
    MarkTemplateRequest,
)
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store
from backend.models.campaign import Campaign, CampaignStatus, TemplateVisibility
from backend.models.user import CampaignMemberRole, User
from backend.models.workspace import WorkspaceRole

router = APIRouter(tags=["campaigns"])


def _resolve_template_parameters(
    template: Campaign,
    overrides: Optional[dict[str, str]],
) -> dict[str, str]:
    """Resolve template parameters using overrides first, then defaults."""
    parameters = template.template_parameters or []
    if not parameters:
        return {}

    incoming = overrides or {}
    missing = [p.name for p in parameters if p.default is None and p.name not in incoming]
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise HTTPException(
            status_code=422,
            detail=f"Missing required template parameters: {missing_list}",
        )

    resolved: dict[str, str] = {}
    for p in parameters:
        if p.name in incoming:
            resolved[p.name] = incoming[p.name]
        elif p.default is not None:
            resolved[p.name] = p.default
    return resolved


def _apply_placeholders_single_pass(raw: str, resolved: dict[str, str]) -> str:
    """Replace {{param}} placeholders in a single pass without recursive expansion."""
    if not raw or not resolved:
        return raw

    with_tokens = raw
    token_values: list[tuple[str, str]] = []
    for idx, (name, value) in enumerate(resolved.items()):
        token = f"{{{{{name}}}}}"
        marker = f"__tmpl_marker_{idx}__"
        with_tokens = with_tokens.replace(token, marker)
        token_values.append((marker, value))

    for marker, value in token_values:
        with_tokens = with_tokens.replace(marker, value)
    return with_tokens


@router.post("/campaigns/{campaign_id}/clone", response_model=CreateCampaignResponse, status_code=201)
async def clone_campaign(
    workspace_id: str,
    campaign_id: str,
    body: CloneCampaignRequest = Body(),
    source_campaign: Campaign = Depends(get_campaign_for_read),
    user: Optional[User] = Depends(get_current_user),
) -> CreateCampaignResponse:
    """Clone a campaign into the same or another workspace with configurable depth."""
    store = get_campaign_store()
    resolved_parameters: dict[str, str] = {}
    if source_campaign.is_template and source_campaign.template_parameters:
        resolved_parameters = _resolve_template_parameters(source_campaign, body.parameter_overrides)

    target_workspace_id = body.target_workspace_id or source_campaign.workspace_id
    if target_workspace_id is None:
        raise HTTPException(status_code=409, detail="Target workspace could not be determined")

    target_workspace = await store.get_workspace(target_workspace_id)
    if target_workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if user is not None and not user.is_admin:
        target_role = await store.get_workspace_member_role(target_workspace_id, user.id)
        if target_role != WorkspaceRole.CREATOR:
            raise HTTPException(
                status_code=403,
                detail="Only workspace CREATORs can clone campaigns into the target workspace",
            )

    clone_campaign_doc = Campaign(
        id=str(uuid4()),
        owner_id=user.id if user is not None else source_campaign.owner_id,
        workspace_id=target_workspace_id,
        status=CampaignStatus.DRAFT,
        brief=source_campaign.brief.model_copy(deep=True),
        review=None,
        stage_errors={},
        version=1,
        wizard_step=0,
        is_template=False,
        template_category=None,
        template_tags=[],
        template_description=None,
        template_visibility=TemplateVisibility.WORKSPACE,
        template_featured=False,
        template_version=1,
        template_parameters=[],
        cloned_from_campaign_id=source_campaign.id,
        cloned_from_template_version=(
            source_campaign.template_version if source_campaign.is_template else None
        ),
        clone_depth=body.depth,
    )

    if body.depth in {"strategy", "content", "full"}:
        clone_campaign_doc.strategy = source_campaign.strategy.model_copy(deep=True) if source_campaign.strategy else None
    if body.depth in {"content", "full"}:
        clone_campaign_doc.content = source_campaign.content.model_copy(deep=True) if source_campaign.content else None
    if body.depth == "full":
        clone_campaign_doc.channel_plan = (
            source_campaign.channel_plan.model_copy(deep=True)
            if source_campaign.channel_plan
            else None
        )
        clone_campaign_doc.analytics_plan = (
            source_campaign.analytics_plan.model_copy(deep=True)
            if source_campaign.analytics_plan
            else None
        )

    if resolved_parameters:
        clone_campaign_doc.brief.product_or_service = _apply_placeholders_single_pass(
            clone_campaign_doc.brief.product_or_service,
            resolved_parameters,
        )
        clone_campaign_doc.brief.goal = _apply_placeholders_single_pass(
            clone_campaign_doc.brief.goal,
            resolved_parameters,
        )
        clone_campaign_doc.brief.additional_context = _apply_placeholders_single_pass(
            clone_campaign_doc.brief.additional_context,
            resolved_parameters,
        )
        if clone_campaign_doc.strategy is not None:
            clone_campaign_doc.strategy.value_proposition = _apply_placeholders_single_pass(
                clone_campaign_doc.strategy.value_proposition,
                resolved_parameters,
            )
            clone_campaign_doc.strategy.positioning = _apply_placeholders_single_pass(
                clone_campaign_doc.strategy.positioning,
                resolved_parameters,
            )
            clone_campaign_doc.strategy.key_messages = [
                _apply_placeholders_single_pass(message, resolved_parameters)
                for message in clone_campaign_doc.strategy.key_messages
            ]

    clone_campaign_doc.updated_at = datetime.utcnow()
    clone_campaign_doc.created_at = clone_campaign_doc.updated_at
    clone_campaign_doc.clarification_questions = []
    clone_campaign_doc.clarification_answers = {}
    clone_campaign_doc.original_content = None
    clone_campaign_doc.content_revision_count = 0

    clone_campaign_doc = await store.update(clone_campaign_doc)

    if user is not None:
        await store.add_member(clone_campaign_doc.id, user.id, CampaignMemberRole.OWNER)

    return CreateCampaignResponse(
        id=clone_campaign_doc.id,
        status=clone_campaign_doc.status.value,
        message="Campaign cloned.",
    )


@router.post("/campaigns/{campaign_id}/mark-template")
async def mark_campaign_as_template(
    workspace_id: str,
    campaign_id: str,
    body: MarkTemplateRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
    user: Optional[User] = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark an approved campaign as a reusable template with metadata."""
    store = get_campaign_store()

    if campaign.status != CampaignStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Only approved campaigns can be marked as templates")

    if user is not None and not user.is_admin:
        ws_role = await store.get_workspace_member_role(campaign.workspace_id or workspace_id, user.id)
        if ws_role != WorkspaceRole.CREATOR:
            raise HTTPException(status_code=403, detail="Only workspace CREATORs can mark templates")

    if body.visibility == TemplateVisibility.ORGANIZATION and (user is None or not user.is_admin):
        raise HTTPException(
            status_code=403,
            detail="Only platform admins can set organization-wide template visibility",
        )

    campaign.is_template = True
    campaign.template_category = body.category
    campaign.template_tags = body.tags
    campaign.template_description = body.description
    campaign.template_visibility = body.visibility
    campaign.template_parameters = body.parameters
    campaign.template_version = 1
    campaign.updated_at = datetime.utcnow()

    updated = await store.update(campaign)

    return {
        "id": updated.id,
        "category": updated.template_category,
        "tags": updated.template_tags,
        "visibility": updated.template_visibility,
        "version": updated.template_version,
    }
