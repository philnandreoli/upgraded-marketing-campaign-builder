"""Add composite indexes for dominant query patterns

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-18 00:00:00.000000

Adds four composite indexes to cover the highest-traffic query patterns:

1. (workspace_id, created_at DESC) on campaigns — used by list_workspace_campaigns()
   which is called on every Dashboard load.
2. (workspace_id, status) on campaigns — used by filtered dashboard queries.
3. (user_id, role) on workspace_members — used by permission checks and workspace
   listing where the join is driven by user_id (the non-leading PK column).
4. (user_id) on campaign_members — used by list_accessible() which joins on
   campaign_members.user_id (the non-leading PK column).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create composite indexes for dominant query patterns."""
    op.create_index(
        "ix_campaigns_workspace_created",
        "campaigns",
        ["workspace_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_campaigns_workspace_status",
        "campaigns",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_workspace_members_user_role",
        "workspace_members",
        ["user_id", "role"],
    )
    op.create_index(
        "ix_campaign_members_user_id",
        "campaign_members",
        ["user_id"],
    )


def downgrade() -> None:
    """Drop composite indexes added in this migration."""
    op.drop_index("ix_campaign_members_user_id", table_name="campaign_members")
    op.drop_index("ix_workspace_members_user_role", table_name="workspace_members")
    op.drop_index("ix_campaigns_workspace_status", table_name="campaigns")
    op.drop_index("ix_campaigns_workspace_created", table_name="campaigns")
