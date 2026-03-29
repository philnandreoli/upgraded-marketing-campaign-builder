"""Template Library API routes."""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response

from backend.apps.api.schemas.campaigns import (
    AdminTemplateAnalytics,
    TemplateRecommendation,
    TemplateMetadata,
    TemplatePreview,
    TemplateStats,
    TemplateSummary,
    UpdateTemplateRequest,
)
from backend.core.rate_limit import limiter
from backend.infrastructure.auth import get_current_user, require_admin, require_authenticated
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.llm_service import get_llm_service
from backend.models.campaign import Campaign, TemplateVisibility
from backend.models.user import User
from backend.services.template_recommender import recommend_templates

router = APIRouter(tags=["templates"])
logger = logging.getLogger(__name__)


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


@router.get("/templates/recommend", response_model=list[TemplateRecommendation])
@limiter.limit("10/minute")
async def recommend_template_list(
    request: Request,
    response: Response,
    goal: str = Query(..., min_length=1),
    product: str = Query(..., min_length=1),
    channels: Optional[str] = Query(default=None, description="Comma-separated channels"),
    budget: Optional[float] = Query(default=None, ge=0),
    user: User = Depends(require_authenticated),
) -> list[TemplateRecommendation]:
    """Recommend best-fit templates using LLM ranking over templates accessible to the user."""
    store = get_campaign_store()
    workspaces = await store.list_workspaces(user.id, is_admin=user.is_admin)
    workspace_ids = [workspace.id for workspace in workspaces]

    try:
        return await recommend_templates(
            goal=goal,
            product=product,
            channels=channels,
            budget=budget,
            user_id=user.id,
            workspace_ids=workspace_ids,
            campaign_store=store,
            llm_service=get_llm_service(),
        )
    except Exception:
        logger.warning("Template recommendation failed unexpectedly; returning empty list", exc_info=True)
        return []


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


@router.get("/templates/{template_id}/stats", response_model=TemplateStats)
async def get_template_stats(
    template_id: str,
    user: User = Depends(require_authenticated),
) -> TemplateStats:
    """Return aggregate performance stats for a single template."""
    store = get_campaign_store()
    template = await store.get(template_id)
    if template is None or not template.is_template:
        raise HTTPException(status_code=404, detail="Template not found")
    if not await _can_access_template(template, user):
        raise HTTPException(status_code=404, detail="Template not found")

    stats = await store.get_template_stats(template_id)
    return TemplateStats(**stats)


@router.get("/admin/templates/analytics", response_model=AdminTemplateAnalytics)
async def get_admin_template_analytics(
    _: User = Depends(require_admin),
) -> AdminTemplateAnalytics:
    """Return admin-only aggregate analytics for template adoption and quality."""
    store = get_campaign_store()
    analytics = await store.get_template_analytics()
    return AdminTemplateAnalytics(**analytics)


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
