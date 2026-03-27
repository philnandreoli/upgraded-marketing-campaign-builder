"""Add composite poll index on workflow_signals

Revision ID: 0019
Revises: 0018
Create Date: 2026-03-27 00:00:00.000000

Adds a composite index on (campaign_id, signal_type, consumed_at, created_at)
to cover the full predicate of poll_signal():

  WHERE campaign_id = ? AND signal_type = ? AND consumed_at IS NULL
  ORDER BY created_at

Without this index every poll cycle requires a sequential scan of all
workflow_signals rows for the given campaign.  The composite index lets
PostgreSQL evaluate the entire WHERE clause from the index and avoid
returning already-consumed rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: Union[str, Sequence[str], None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite poll index on workflow_signals."""
    op.create_index(
        "ix_workflow_signals_poll",
        "workflow_signals",
        ["campaign_id", "signal_type", "consumed_at", "created_at"],
    )


def downgrade() -> None:
    """Drop composite poll index from workflow_signals."""
    op.drop_index("ix_workflow_signals_poll", table_name="workflow_signals")
