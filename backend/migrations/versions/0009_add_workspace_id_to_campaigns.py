"""Add workspace_id column to campaigns table

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-07 00:00:00.000000

Adds a nullable workspace_id FK column to the campaigns table.
Existing rows will simply get NULL — no data migration is needed.
The operation is idempotent: the column is only added if it does not
already exist.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add workspace_id FK column to campaigns if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("campaigns")}

    if "workspace_id" not in existing_columns:
        op.add_column(
            "campaigns",
            sa.Column(
                "workspace_id",
                sa.String(),
                sa.ForeignKey("workspaces.id"),
                nullable=True,
            ),
        )
        op.create_index("ix_campaigns_workspace_id", "campaigns", ["workspace_id"])


def downgrade() -> None:
    """Remove workspace_id column and its index from the campaigns table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("campaigns")}

    if "workspace_id" in existing_columns:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("campaigns")}
        if "ix_campaigns_workspace_id" in existing_indexes:
            op.drop_index("ix_campaigns_workspace_id", table_name="campaigns")
        op.drop_column("campaigns", "workspace_id")
