"""
Campaign comment routes.

Endpoints:
  POST   /api/workspaces/{workspace_id}/campaigns/{campaign_id}/comments
      — Create a new comment (requires WRITE)
  GET    /api/workspaces/{workspace_id}/campaigns/{campaign_id}/comments
      — List comments, filterable by ?section= and ?piece_index= (requires READ)
  GET    /api/workspaces/{workspace_id}/campaigns/{campaign_id}/comments/count
      — Return { unresolved: N } (requires READ)
  PATCH  /api/workspaces/{workspace_id}/campaigns/{campaign_id}/comments/{comment_id}
      — Update comment body (author-only + WRITE)
  DELETE /api/workspaces/{workspace_id}/campaigns/{campaign_id}/comments/{comment_id}
      — Delete a comment (author-only or admin + WRITE)
  PATCH  /api/workspaces/{workspace_id}/campaigns/{campaign_id}/comments/{comment_id}/resolve
      — Toggle resolved state (requires WRITE)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.models.campaign import Campaign, CommentSection
from backend.models.user import User, UserRole
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.comment_store import get_comment_store

from backend.api.websocket import manager as ws_manager
from backend.apps.api.dependencies import get_campaign_for_read, get_campaign_for_write
from backend.apps.api.schemas.comments import (
    CommentResponse,
    CreateCommentRequest,
    UpdateCommentRequest,
)

router = APIRouter(tags=["campaign-comments"])


def _is_admin(user: User) -> bool:
    return UserRole.ADMIN in user.roles


@router.post(
    "/campaigns/{campaign_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
async def create_comment(
    campaign_id: str,
    body: CreateCommentRequest,
    campaign: Campaign = Depends(get_campaign_for_write),
    user: Optional[User] = Depends(get_current_user),
) -> CommentResponse:
    """Create a new comment on a campaign section. Requires WRITE access."""
    store = get_comment_store()
    comment = await store.create(
        campaign_id=campaign.id,
        author_id=user.id,
        body=body.body,
        section=body.section,
        parent_id=body.parent_id,
        content_piece_index=body.content_piece_index,
    )
    response = CommentResponse(
        id=comment.id,
        campaign_id=comment.campaign_id,
        parent_id=comment.parent_id,
        section=comment.section,
        content_piece_index=comment.content_piece_index,
        body=comment.body,
        author_id=comment.author_id,
        is_resolved=comment.is_resolved,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )
    await ws_manager.broadcast({
        "type": "comment_added",
        "campaign_id": campaign.id,
        "comment": response.model_dump(mode="json"),
    })
    return response


@router.get(
    "/campaigns/{campaign_id}/comments/count",
    response_model=dict,
)
async def count_comments(
    campaign_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
) -> dict:
    """Return the count of unresolved comments for a campaign. Requires READ access."""
    store = get_comment_store()
    unresolved = await store.count_unresolved(campaign.id)
    return {"unresolved": unresolved}


@router.get(
    "/campaigns/{campaign_id}/comments",
    response_model=list[CommentResponse],
)
async def list_comments(
    campaign_id: str,
    campaign: Campaign = Depends(get_campaign_for_read),
    section: Optional[CommentSection] = Query(default=None, description="Filter by campaign section."),
    piece_index: Optional[int] = Query(default=None, description="Filter by content piece index."),
) -> list[CommentResponse]:
    """List comments for a campaign. Requires READ access."""
    store = get_comment_store()
    comments = await store.list_by_campaign(
        campaign_id=campaign.id,
        section=section,
        content_piece_index=piece_index,
    )
    return [
        CommentResponse(
            id=c.id,
            campaign_id=c.campaign_id,
            parent_id=c.parent_id,
            section=c.section,
            content_piece_index=c.content_piece_index,
            body=c.body,
            author_id=c.author_id,
            is_resolved=c.is_resolved,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in comments
    ]


@router.patch(
    "/campaigns/{campaign_id}/comments/{comment_id}",
    response_model=CommentResponse,
)
async def update_comment(
    campaign_id: str,
    comment_id: str,
    body: UpdateCommentRequest,
    campaign: Campaign = Depends(get_campaign_for_write),
    user: Optional[User] = Depends(get_current_user),
) -> CommentResponse:
    """Update a comment body. Only the comment author (or an admin) may edit. Requires WRITE access."""
    store = get_comment_store()
    comment = await store.get(comment_id)
    if comment is None or comment.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not _is_admin(user) and comment.author_id != user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own comments")
    updated = await store.update(comment_id, body.body)
    response = CommentResponse(
        id=updated.id,
        campaign_id=updated.campaign_id,
        parent_id=updated.parent_id,
        section=updated.section,
        content_piece_index=updated.content_piece_index,
        body=updated.body,
        author_id=updated.author_id,
        is_resolved=updated.is_resolved,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )
    await ws_manager.broadcast({
        "type": "comment_updated",
        "campaign_id": updated.campaign_id,
        "comment": response.model_dump(mode="json"),
    })
    return response


@router.delete(
    "/campaigns/{campaign_id}/comments/{comment_id}",
    status_code=204,
    response_class=Response,
)
async def delete_comment(
    campaign_id: str,
    comment_id: str,
    campaign: Campaign = Depends(get_campaign_for_write),
    user: Optional[User] = Depends(get_current_user),
) -> Response:
    """Delete a comment. Only the comment author or an admin may delete. Requires WRITE access."""
    store = get_comment_store()
    comment = await store.get(comment_id)
    if comment is None or comment.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not _is_admin(user) and comment.author_id != user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    await store.delete(comment_id)
    await ws_manager.broadcast({
        "type": "comment_deleted",
        "campaign_id": campaign.id,
        "comment_id": comment_id,
    })
    return Response(status_code=204)


@router.patch(
    "/campaigns/{campaign_id}/comments/{comment_id}/resolve",
    response_model=CommentResponse,
)
async def resolve_comment(
    campaign_id: str,
    comment_id: str,
    campaign: Campaign = Depends(get_campaign_for_write),
    resolved: bool = Query(default=True, description="Set to false to unresolve."),
) -> CommentResponse:
    """Toggle the resolved state of a comment. Requires WRITE access."""
    store = get_comment_store()
    comment = await store.get(comment_id)
    if comment is None or comment.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    updated = await store.resolve(comment_id, resolved=resolved)
    response = CommentResponse(
        id=updated.id,
        campaign_id=updated.campaign_id,
        parent_id=updated.parent_id,
        section=updated.section,
        content_piece_index=updated.content_piece_index,
        body=updated.body,
        author_id=updated.author_id,
        is_resolved=updated.is_resolved,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )
    await ws_manager.broadcast({
        "type": "comment_resolved",
        "campaign_id": updated.campaign_id,
        "comment_id": comment_id,
        "is_resolved": updated.is_resolved,
    })
    return response
