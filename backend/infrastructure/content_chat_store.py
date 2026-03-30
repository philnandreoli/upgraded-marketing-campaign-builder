"""
PostgreSQL-backed content chat store.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import delete as sa_delete, distinct, func, select, update as sa_update

from backend.infrastructure.database import ContentChatMessageRow, async_session
from backend.models.chat import ContentChatMessage


class ContentChatStore:
    """Repository for campaign content-approval chat messages."""

    async def create_message(
        self,
        campaign_id: str,
        piece_index: int,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ContentChatMessage:
        message = ContentChatMessage(
            id=str(uuid.uuid4()),
            campaign_id=campaign_id,
            piece_index=piece_index,
            role=role,
            content=content,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            user_id=user_id,
        )
        row = ContentChatMessageRow(
            id=message.id,
            campaign_id=message.campaign_id,
            piece_index=message.piece_index,
            role=message.role,
            content=message.content,
            metadata_json=message.metadata,
            created_at=message.created_at,
            user_id=message.user_id,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return message

    async def get_history(
        self,
        campaign_id: str,
        piece_index: int,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ContentChatMessage], int]:
        async with async_session() as session:
            total_res = await session.execute(
                select(func.count()).select_from(ContentChatMessageRow).where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.piece_index == piece_index,
                )
            )
            total = int(total_res.scalar_one())

            result = await session.execute(
                select(ContentChatMessageRow)
                .where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.piece_index == piece_index,
                )
                .order_by(ContentChatMessageRow.created_at.asc())
                .offset(offset)
                .limit(limit)
            )
            messages = [_row_to_model(row) for row in result.scalars().all()]
            return messages, total

    async def delete_last_exchange(self, campaign_id: str, piece_index: int) -> None:
        async with async_session() as session:
            assistant_res = await session.execute(
                select(ContentChatMessageRow)
                .where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.piece_index == piece_index,
                    ContentChatMessageRow.role == "assistant",
                )
                .order_by(ContentChatMessageRow.created_at.desc())
                .limit(1)
            )
            assistant_row = assistant_res.scalar_one_or_none()
            if assistant_row is None:
                return

            user_res = await session.execute(
                select(ContentChatMessageRow)
                .where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.piece_index == piece_index,
                    ContentChatMessageRow.role == "user",
                    ContentChatMessageRow.created_at <= assistant_row.created_at,
                )
                .order_by(ContentChatMessageRow.created_at.desc())
                .limit(1)
            )
            user_row = user_res.scalar_one_or_none()

            ids_to_delete = [assistant_row.id]
            if user_row is not None:
                ids_to_delete.append(user_row.id)

            await session.execute(
                sa_delete(ContentChatMessageRow).where(ContentChatMessageRow.id.in_(ids_to_delete))
            )
            await session.commit()

    async def get_message(self, message_id: str) -> Optional[ContentChatMessage]:
        async with async_session() as session:
            row = await session.get(ContentChatMessageRow, message_id)
            if row is None:
                return None
            return _row_to_model(row)

    async def update_message_metadata(self, message_id: str, metadata: dict[str, Any]) -> None:
        async with async_session() as session:
            await session.execute(
                sa_update(ContentChatMessageRow)
                .where(ContentChatMessageRow.id == message_id)
                .values(metadata_json=metadata)
            )
            await session.commit()

    async def get_last_non_reverted_assistant_message(
        self,
        campaign_id: str,
        piece_index: int,
    ) -> Optional[ContentChatMessage]:
        async with async_session() as session:
            result = await session.execute(
                select(ContentChatMessageRow)
                .where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.piece_index == piece_index,
                    ContentChatMessageRow.role == "assistant",
                )
                .order_by(ContentChatMessageRow.created_at.desc())
            )
            for row in result.scalars().all():
                metadata = row.metadata_json or {}
                if not bool(metadata.get("reverted", False)):
                    return _row_to_model(row)
            return None

    async def get_suggestions_message(
        self,
        campaign_id: str,
        piece_index: int,
    ) -> Optional[ContentChatMessage]:
        async with async_session() as session:
            result = await session.execute(
                select(ContentChatMessageRow)
                .where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.piece_index == piece_index,
                    ContentChatMessageRow.role == "system",
                )
                .order_by(ContentChatMessageRow.created_at.desc())
            )
            for row in result.scalars().all():
                metadata = row.metadata_json or {}
                if metadata.get("type") == "suggestions":
                    return _row_to_model(row)
            return None

    async def get_stats(self, campaign_id: str) -> dict[str, Any]:
        async with async_session() as session:
            total_refinements_res = await session.execute(
                select(func.count()).select_from(ContentChatMessageRow).where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.role == "user",
                )
            )
            total_refinements = int(total_refinements_res.scalar_one())

            total_reverts_res = await session.execute(
                select(func.count()).select_from(ContentChatMessageRow).where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.metadata_json["reverted"].as_boolean() == True,  # noqa: E712
                )
            )
            total_reverts = int(total_reverts_res.scalar_one())

            approved_from_chat_res = await session.execute(
                select(func.count(distinct(ContentChatMessageRow.piece_index))).where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.role == "assistant",
                    ContentChatMessageRow.metadata_json["type"].as_string() == "apply_and_approve",
                )
            )
            pieces_approved_from_chat = int(approved_from_chat_res.scalar_one())

            instruction_type_res = await session.execute(
                select(
                    ContentChatMessageRow.metadata_json["instruction_type"].as_string().label("instruction_type"),
                    func.count().label("count"),
                )
                .where(
                    ContentChatMessageRow.campaign_id == campaign_id,
                    ContentChatMessageRow.role == "user",
                    ContentChatMessageRow.metadata_json["instruction_type"].as_string().is_not(None),
                )
                .group_by(ContentChatMessageRow.metadata_json["instruction_type"].as_string())
                .order_by(func.count().desc())
            )
            top_instruction_types = {
                str(row.instruction_type): int(row.count)
                for row in instruction_type_res.all()
                if row.instruction_type is not None
            }

        return {
            "total_refinements": total_refinements,
            "total_reverts": total_reverts,
            "pieces_approved_from_chat": pieces_approved_from_chat,
            "top_instruction_types": top_instruction_types,
        }


def _row_to_model(row: ContentChatMessageRow) -> ContentChatMessage:
    return ContentChatMessage(
        id=row.id,
        campaign_id=row.campaign_id,
        piece_index=row.piece_index,
        role=row.role,
        content=row.content,
        metadata=row.metadata_json or {},
        created_at=row.created_at,
        user_id=row.user_id,
    )


_store: ContentChatStore | None = None


def get_content_chat_store() -> ContentChatStore:
    global _store
    if _store is None:
        _store = ContentChatStore()
    return _store
