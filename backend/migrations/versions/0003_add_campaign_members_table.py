"""Add campaign_members table

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-04 00:00:00.000000

Creates the campaign_members join table that associates users with campaigns
and records a per-campaign role (owner, editor, viewer).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the campaign_members table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "campaign_members" not in tables:
        op.create_table(
            "campaign_members",
            sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("added_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    """Drop the campaign_members table."""
    op.drop_table("campaign_members")
