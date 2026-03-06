"""Add workflow_checkpoints table

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-06 00:00:00.000000

Creates the workflow_checkpoints table that persists the coordinator's
durable pipeline state (active stage, wait type, revision cycle, etc.)
so that workflows can survive server restarts.

No changes are made to existing tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the workflow_checkpoints table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "workflow_checkpoints" not in tables:
        op.create_table(
            "workflow_checkpoints",
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("current_stage", sa.String(), nullable=False),
            sa.Column("wait_type", sa.String(), nullable=True),
            sa.Column("revision_cycle", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("resume_token", sa.String(), nullable=True),
            sa.Column("context", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    """Drop the workflow_checkpoints table."""
    op.drop_table("workflow_checkpoints")
