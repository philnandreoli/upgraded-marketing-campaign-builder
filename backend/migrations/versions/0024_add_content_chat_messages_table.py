"""Add content_chat_messages table

Revision ID: 0024
Revises: 0023
Create Date: 2026-03-30 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: Union[str, Sequence[str], None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_names(bind, table_name: str) -> set[str]:
    inspector = inspect(bind)
    try:
        return {idx["name"] for idx in inspector.get_indexes(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    """Create content chat message table and indexes if they do not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "content_chat_messages" not in tables:
        op.create_table(
            "content_chat_messages",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("piece_index", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )

    indexes = _index_names(bind, "content_chat_messages")
    if "ix_content_chat_messages_campaign_id" not in indexes:
        op.create_index(
            "ix_content_chat_messages_campaign_id",
            "content_chat_messages",
            ["campaign_id"],
        )
    if "ix_content_chat_messages_campaign_piece" not in indexes:
        op.create_index(
            "ix_content_chat_messages_campaign_piece",
            "content_chat_messages",
            ["campaign_id", "piece_index", "created_at"],
        )


def downgrade() -> None:
    """Drop content chat message indexes and table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "content_chat_messages" not in tables:
        return

    indexes = _index_names(bind, "content_chat_messages")
    if "ix_content_chat_messages_campaign_piece" in indexes:
        op.drop_index("ix_content_chat_messages_campaign_piece", table_name="content_chat_messages")
    if "ix_content_chat_messages_campaign_id" in indexes:
        op.drop_index("ix_content_chat_messages_campaign_id", table_name="content_chat_messages")
    op.drop_table("content_chat_messages")

