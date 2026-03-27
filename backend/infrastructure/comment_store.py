"""
PostgreSQL-backed comment store.

Persists campaign comments in the 'campaign_comments' table.
All methods are async and use the shared session factory from
``backend.infrastructure.database``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sa_delete, func, select, update as sa_update

from backend.models.campaign import CampaignComment, CommentSection
from backend.infrastructure.database import CampaignCommentRow, async_session


class CommentStore:
    """Comment repository backed by PostgreSQL."""

    # ------------------------------------------------------------------
    # Comment CRUD — all async
    # ------------------------------------------------------------------

    async def create(
        self,
        campaign_id: str,
        author_id: str,
        body: str,
        section: CommentSection,
        parent_id: Optional[str] = None,
        content_piece_index: Optional[int] = None,
    ) -> CampaignComment:
        """Create and persist a new comment, returning the domain object."""
        comment = CampaignComment(
            campaign_id=campaign_id,
            author_id=author_id,
            body=body,
            section=section,
            parent_id=parent_id,
            content_piece_index=content_piece_index,
        )
        row = CampaignCommentRow(
            id=comment.id,
            campaign_id=comment.campaign_id,
            author_id=comment.author_id,
            body=comment.body,
            section=comment.section.value,
            parent_id=comment.parent_id,
            content_piece_index=comment.content_piece_index,
            is_resolved=comment.is_resolved,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return comment

    async def get(self, comment_id: str) -> Optional[CampaignComment]:
        """Return a single comment by ID, or ``None`` if not found."""
        async with async_session() as session:
            row = await session.get(CampaignCommentRow, comment_id)
            if row is None:
                return None
            return _row_to_model(row)

    async def list_by_campaign(
        self,
        campaign_id: str,
        section: Optional[CommentSection] = None,
        content_piece_index: Optional[int] = None,
    ) -> list[CampaignComment]:
        """Return all comments for a campaign, with optional filters."""
        async with async_session() as session:
            stmt = select(CampaignCommentRow).where(
                CampaignCommentRow.campaign_id == campaign_id
            )
            if section is not None:
                stmt = stmt.where(CampaignCommentRow.section == section.value)
            if content_piece_index is not None:
                stmt = stmt.where(
                    CampaignCommentRow.content_piece_index == content_piece_index
                )
            result = await session.execute(stmt)
            return [_row_to_model(row) for row in result.scalars().all()]

    async def update(self, comment_id: str, body: str) -> CampaignComment:
        """Update the body of an existing comment.

        Raises ``ValueError`` if the comment does not exist.
        """
        now = datetime.utcnow()
        async with async_session() as session:
            result = await session.execute(
                sa_update(CampaignCommentRow)
                .where(CampaignCommentRow.id == comment_id)
                .values(body=body, updated_at=now)
                .returning(CampaignCommentRow)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"Comment {comment_id!r} not found")
            await session.commit()
            return _row_to_model(row)

    async def delete(self, comment_id: str) -> None:
        """Delete a comment and cascade-delete its replies."""
        async with async_session() as session:
            # Delete all child replies first (FK constraint, no DB cascade).
            await session.execute(
                sa_delete(CampaignCommentRow).where(
                    CampaignCommentRow.parent_id == comment_id
                )
            )
            await session.execute(
                sa_delete(CampaignCommentRow).where(
                    CampaignCommentRow.id == comment_id
                )
            )
            await session.commit()

    async def resolve(self, comment_id: str, resolved: bool = True) -> CampaignComment:
        """Set the resolved state of a comment.

        Raises ``ValueError`` if the comment does not exist.
        """
        now = datetime.utcnow()
        async with async_session() as session:
            result = await session.execute(
                sa_update(CampaignCommentRow)
                .where(CampaignCommentRow.id == comment_id)
                .values(is_resolved=resolved, updated_at=now)
                .returning(CampaignCommentRow)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"Comment {comment_id!r} not found")
            await session.commit()
            return _row_to_model(row)

    async def count_unresolved(self, campaign_id: str) -> int:
        """Return the number of unresolved comments for *campaign_id*."""
        async with async_session() as session:
            result = await session.execute(
                select(func.count()).where(
                    CampaignCommentRow.campaign_id == campaign_id,
                    CampaignCommentRow.is_resolved == False,  # noqa: E712
                )
            )
            return result.scalar_one()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_model(row: CampaignCommentRow) -> CampaignComment:
    """Convert an ORM row to a ``CampaignComment`` domain object."""
    return CampaignComment(
        id=row.id,
        campaign_id=row.campaign_id,
        author_id=row.author_id,
        body=row.body,
        section=CommentSection(row.section),
        parent_id=row.parent_id,
        content_piece_index=row.content_piece_index,
        is_resolved=row.is_resolved,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: CommentStore | None = None


def get_comment_store() -> CommentStore:
    """Return the module-level ``CommentStore`` singleton."""
    global _store
    if _store is None:
        _store = CommentStore()
    return _store
