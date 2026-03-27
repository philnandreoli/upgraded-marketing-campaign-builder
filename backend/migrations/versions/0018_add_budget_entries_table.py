"""Add budget_entries table

Revision ID: 0018
Revises: 0017
Create Date: 2026-03-27 00:00:00.000000

Creates the budget_entries table for campaign-level planned and actual spend
tracking, used by budget forecasting and workspace budget overviews.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: Union[str, Sequence[str], None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create budget_entries table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "budget_entries" not in tables:
        op.create_table(
            "budget_entries",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("entry_type", sa.String(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("entry_date", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    indexes = {idx["name"] for idx in inspect(bind).get_indexes("budget_entries")}
    if "ix_budget_entries_campaign_id" not in indexes:
        op.create_index(
            "ix_budget_entries_campaign_id",
            "budget_entries",
            ["campaign_id"],
        )
    if "ix_budget_entries_campaign_type" not in indexes:
        op.create_index(
            "ix_budget_entries_campaign_type",
            "budget_entries",
            ["campaign_id", "entry_type"],
        )


def downgrade() -> None:
    """Drop budget_entries table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "budget_entries" in tables:
        op.drop_table("budget_entries")
