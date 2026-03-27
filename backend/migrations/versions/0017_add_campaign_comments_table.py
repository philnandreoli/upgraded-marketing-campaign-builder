"""Add campaign_comments table

Revision ID: 0017
Revises: 0016
Create Date: 2026-03-27 00:00:00.000000

Creates the campaign_comments table for storing per-section comment threads
on campaigns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: Union[str, Sequence[str], None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create campaign_comments table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "campaign_comments" not in tables:
        op.create_table(
            "campaign_comments",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "parent_id",
                sa.String(),
                sa.ForeignKey("campaign_comments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("section", sa.String(), nullable=False),
            sa.Column("content_piece_index", sa.Integer(), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("author_id", sa.String(), nullable=False),
            sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("campaign_comments")}
    if "ix_campaign_comments_campaign_id" not in indexes:
        op.create_index("ix_campaign_comments_campaign_id", "campaign_comments", ["campaign_id"])
    if "ix_campaign_comments_parent_id" not in indexes:
        op.create_index("ix_campaign_comments_parent_id", "campaign_comments", ["parent_id"])


def downgrade() -> None:
    """Drop campaign_comments table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "campaign_comments" in tables:
        op.drop_table("campaign_comments")
