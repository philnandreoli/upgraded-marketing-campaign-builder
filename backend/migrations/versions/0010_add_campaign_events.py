"""Add campaign_events table

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-13 00:00:00.000000

Creates the campaign_events table that persists all pipeline events emitted
by the CoordinatorAgent, providing a durable audit trail for campaign pipeline
execution.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the campaign_events table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "campaign_events" not in tables:
        op.create_table(
            "campaign_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("stage", sa.String(), nullable=True),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_campaign_events_campaign_id",
            "campaign_events",
            ["campaign_id"],
        )


def downgrade() -> None:
    """Drop the campaign_events table."""
    op.drop_index("ix_campaign_events_campaign_id", table_name="campaign_events")
    op.drop_table("campaign_events")
