"""
PostgreSQL-backed comment store.

Persists campaign comment threads in the ``campaign_comments`` table.
All methods are async and use the shared session factory from
``backend/infrastructure/database.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sa_delete, func, select, update as sa_update

from backend.infrastructure.database import CampaignCommentRow, async_session
from backend.models.campaign import CampaignComment, CommentSection


class CommentStore:
    """Comment repository backed by PostgreSQL."""

    # ------------------------------------------------------------------
    # CRUD operations — all async
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
        """Insert a new comment row and return the persisted model."""
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
            parent_id=comment.parent_id,
            section=comment.section.value,
            content_piece_index=comment.content_piece_index,
            body=comment.body,
            author_id=comment.author_id,
            is_resolved=comment.is_resolved,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return self._to_model(row)

    async def get(self, comment_id: str) -> Optional[CampaignComment]:
        """Return one comment by ID, or ``None`` if not found."""
        async with async_session() as session:
            row = await session.get(CampaignCommentRow, comment_id)
            if row is None:
                return None
        return self._to_model(row)

    async def list_by_campaign(
        self,
        campaign_id: str,
        section: Optional[CommentSection] = None,
        content_piece_index: Optional[int] = None,
    ) -> list[CampaignComment]:
        """Return all comments for a campaign, optionally filtered.

        *section* filters by campaign section.
        *content_piece_index* further narrows results to a specific content piece
        (only meaningful when ``section=CommentSection.CONTENT``).

        Results are ordered by ``created_at`` ascending (chronological order).
        """
        stmt = (
            select(CampaignCommentRow)
            .where(CampaignCommentRow.campaign_id == campaign_id)
            .order_by(CampaignCommentRow.created_at.asc())
        )
        if section is not None:
            stmt = stmt.where(CampaignCommentRow.section == section.value)
        if content_piece_index is not None:
            stmt = stmt.where(CampaignCommentRow.content_piece_index == content_piece_index)

        async with async_session() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_model(row) for row in rows]

    async def update(self, comment_id: str, body: str) -> CampaignComment:
        """Update the body of an existing comment and return the updated model.

        Raises :class:`KeyError` if the comment does not exist.
        """
        now = datetime.utcnow()
        async with async_session() as session:
            await session.execute(
                sa_update(CampaignCommentRow)
                .where(CampaignCommentRow.id == comment_id)
                .values(body=body, updated_at=now)
            )
            await session.commit()
            row = await session.get(CampaignCommentRow, comment_id)
        if row is None:
            raise KeyError(f"Comment {comment_id!r} not found")
        return self._to_model(row)

    async def delete(self, comment_id: str) -> None:
        """Delete a comment by ID.

        Child replies whose ``parent_id`` references *comment_id* will have
        their ``parent_id`` set to ``NULL`` (handled by the ``ON DELETE SET NULL``
        FK constraint), effectively promoting them to top-level comments.
        """
        async with async_session() as session:
            await session.execute(
                sa_delete(CampaignCommentRow).where(CampaignCommentRow.id == comment_id)
            )
            await session.commit()

    async def resolve(self, comment_id: str, resolved: bool = True) -> CampaignComment:
        """Set or clear the ``is_resolved`` flag on a comment.

        Raises :class:`KeyError` if the comment does not exist.
        """
        now = datetime.utcnow()
        async with async_session() as session:
            await session.execute(
                sa_update(CampaignCommentRow)
                .where(CampaignCommentRow.id == comment_id)
                .values(is_resolved=resolved, updated_at=now)
            )
            await session.commit()
            row = await session.get(CampaignCommentRow, comment_id)
        if row is None:
            raise KeyError(f"Comment {comment_id!r} not found")
        return self._to_model(row)

    async def count_unresolved(self, campaign_id: str) -> int:
        """Return the count of unresolved comments for a campaign.

        Used to populate the badge counter on campaign cards.
        """
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(CampaignCommentRow)
                .where(
                    CampaignCommentRow.campaign_id == campaign_id,
                    CampaignCommentRow.is_resolved == False,  # noqa: E712
                )
            )
            return result.scalar_one()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_model(row: CampaignCommentRow) -> CampaignComment:
        return CampaignComment(
            id=row.id,
            campaign_id=row.campaign_id,
            parent_id=row.parent_id,
            section=CommentSection(row.section),
            content_piece_index=row.content_piece_index,
            body=row.body,
            author_id=row.author_id,
            is_resolved=row.is_resolved,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_comment_store: CommentStore | None = None


def get_comment_store() -> CommentStore:
    global _comment_store
    if _comment_store is None:
        _comment_store = CommentStore()
    return _comment_store
