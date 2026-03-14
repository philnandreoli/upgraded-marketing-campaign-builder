"""Make workspace_id non-nullable on campaigns table

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-14 00:00:00.000000

All campaigns must belong to a workspace.  This migration:
1. Deletes any campaigns that have workspace_id = NULL (orphaned campaigns
   that cannot be assigned to a workspace).
2. Makes the workspace_id column NOT NULL.

If you need to preserve orphaned campaigns, manually assign them to a
workspace before running this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make workspace_id non-nullable, removing any orphaned campaigns first."""
    bind = op.get_bind()

    # Delete orphaned campaigns (workspace_id IS NULL) so we can set NOT NULL.
    # Also remove their related members and events to satisfy FK constraints.
    bind.execute(
        text(
            "DELETE FROM campaign_members WHERE campaign_id IN "
            "(SELECT id FROM campaigns WHERE workspace_id IS NULL)"
        )
    )
    bind.execute(
        text(
            "DELETE FROM campaign_events WHERE campaign_id IN "
            "(SELECT id FROM campaigns WHERE workspace_id IS NULL)"
        )
    )
    bind.execute(text("DELETE FROM campaigns WHERE workspace_id IS NULL"))

    # Now make the column NOT NULL.
    inspector = inspect(bind)
    existing_columns = {c["name"]: c for c in inspector.get_columns("campaigns")}

    if "workspace_id" in existing_columns:
        col = existing_columns["workspace_id"]
        if col.get("nullable", True):
            op.alter_column(
                "campaigns",
                "workspace_id",
                existing_type=sa.String(),
                nullable=False,
            )


def downgrade() -> None:
    """Revert workspace_id back to nullable."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"]: c for c in inspector.get_columns("campaigns")}

    if "workspace_id" in existing_columns:
        col = existing_columns["workspace_id"]
        if not col.get("nullable", True):
            op.alter_column(
                "campaigns",
                "workspace_id",
                existing_type=sa.String(),
                nullable=True,
            )
