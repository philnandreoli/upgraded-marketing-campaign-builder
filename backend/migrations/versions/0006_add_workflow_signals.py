"""Add workflow_signals table

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-07 00:00:00.000000

Creates the workflow_signals table that stores durable human-input signals
(clarification responses, content approvals) so that coordinator wait gates
can poll the database instead of relying on in-memory asyncio.Futures.

This enables cross-process execution: an API worker can write a signal row
and a coordinator worker will pick it up on the next poll cycle.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the workflow_signals table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "workflow_signals" not in tables:
        op.create_table(
            "workflow_signals",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("signal_type", sa.String(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_workflow_signals_campaign_id",
            "workflow_signals",
            ["campaign_id"],
        )


def downgrade() -> None:
    """Drop the workflow_signals table."""
    op.drop_index("ix_workflow_signals_campaign_id", table_name="workflow_signals")
    op.drop_table("workflow_signals")
