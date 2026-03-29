"""Template Library API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

from backend.apps.api.schemas.campaigns import (
    TemplateMetadata,
    TemplatePreview,
    TemplateSummary,
    UpdateTemplateRequest,
)
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store
from backend.models.campaign import Campaign, TemplateVisibility
from backend.models.user import User

router = APIRouter(tags=["templates"])


async def _can_access_template(template: Campaign, user: Optional[User]) -> bool:
    """Return whether the current user can read the given template."""
    if user is None or user.is_admin:
        return True
    if template.template_visibility == TemplateVisibility.ORGANIZATION:
        return True
    if template.workspace_id is None:
        return False
    role = await get_campaign_store().get_workspace_member_role(template.workspace_id, user.id)
    return role is not None


@router.get("/templates", response_model=list[TemplateSummary])
async def list_templates(
    response: Response,
    category: Optional[str] = Query(default=None),
    tags: Optional[str] = Query(default=None, description="Comma-separated tag list"),
    featured: Optional[bool] = Query(default=None),
    visibility: Optional[TemplateVisibility] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: Optional[User] = Depends(get_current_user),
) -> list[TemplateSummary]:
    """List templates visible to the current user with template filters."""
    store = get_campaign_store()

    workspace_ids: list[str] = []
    is_admin = True if user is None else user.is_admin
    if user is not None and not user.is_admin:
        workspaces = await store.list_workspaces(user.id, is_admin=False)
        workspace_ids = [w.id for w in workspaces]

    tags_filter = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
    items, total_count = await store.list_templates(
        user_id=user.id if user is not None else None,
        workspace_ids=workspace_ids,
        filters={
            "category": category,
            "tags": tags_filter,
            "featured": featured,
            "visibility": visibility.value if visibility is not None else None,
            "search": search,
            "limit": limit,
            "offset": offset,
            "is_admin": is_admin,
        },
    )

    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Offset"] = str(offset)
    response.headers["X-Limit"] = str(limit)

    return [
        TemplateSummary(
            id=item["id"],
            name=item["name"],
            category=item["category"],
            tags=item["tags"],
            description=item["description"],
            visibility=TemplateVisibility(item["visibility"]),
            featured=item["featured"],
            version=item["version"],
            clone_count=item["clone_count"],
            avg_brand_score=item["avg_brand_score"],
            created_at=item["created_at"],
        )
        for item in items
    ]


@router.get("/templates/{campaign_id}/preview", response_model=TemplatePreview)
async def preview_template(
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> TemplatePreview:
    """Return full read-only template preview payload."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None or not campaign.is_template:
        raise HTTPException(status_code=404, detail="Template not found")
    if not await _can_access_template(campaign, user):
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplatePreview.model_validate(campaign.model_dump())


@router.patch("/templates/{campaign_id}", response_model=TemplateMetadata)
async def update_template_metadata(
    campaign_id: str,
    body: UpdateTemplateRequest = Body(),
    user: Optional[User] = Depends(get_current_user),
) -> TemplateMetadata:
    """Update template metadata and increment template version."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None or not campaign.is_template:
        raise HTTPException(status_code=404, detail="Template not found")

    if user is not None and not user.is_admin and campaign.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the template owner or an admin can update templates")

    if body.featured is not None and (user is None or not user.is_admin):
        raise HTTPException(status_code=403, detail="Only platform admins can set featured templates")

    if (
        body.visibility == TemplateVisibility.ORGANIZATION
        and (user is None or not user.is_admin)
    ):
        raise HTTPException(
            status_code=403,
            detail="Only platform admins can set organization-wide template visibility",
        )

    if body.category is not None:
        campaign.template_category = body.category
    if body.tags is not None:
        campaign.template_tags = body.tags
    if body.description is not None:
        campaign.template_description = body.description
    if body.visibility is not None:
        campaign.template_visibility = body.visibility
    if body.featured is not None:
        campaign.template_featured = body.featured
    if body.parameters is not None:
        campaign.template_parameters = body.parameters

    campaign.template_version = int(campaign.template_version or 1) + 1
    campaign.updated_at = datetime.utcnow()
    updated = await store.update(campaign)

    return TemplateMetadata(
        category=updated.template_category,
        tags=updated.template_tags,
        description=updated.template_description,
        visibility=updated.template_visibility,
        featured=updated.template_featured,
        version=updated.template_version,
    )


@router.delete("/templates/{campaign_id}")
async def unmark_template(
    campaign_id: str,
    user: Optional[User] = Depends(get_current_user),
) -> dict[str, Any]:
    """Unmark a campaign as a template without deleting the campaign."""
    store = get_campaign_store()
    campaign = await store.get(campaign_id)
    if campaign is None or not campaign.is_template:
        raise HTTPException(status_code=404, detail="Template not found")

    if user is not None and not user.is_admin and campaign.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the template owner or an admin can unmark templates")

    campaign.is_template = False
    campaign.updated_at = datetime.utcnow()
    await store.update(campaign)
    return {"ok": True, "id": campaign.id, "message": "Campaign unmarked as template"}
