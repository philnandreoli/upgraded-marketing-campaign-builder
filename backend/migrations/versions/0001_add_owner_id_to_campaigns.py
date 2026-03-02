"""Add owner_id column to campaigns table

Revision ID: 0001
Revises:
Create Date: 2026-03-01 00:00:00.000000

This is the initial migration.  It creates the campaigns table if it
does not yet exist, and adds the owner_id column if the table already
exists but is missing that column (upgrade from a pre-auth deployment).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the campaigns table (if absent) or add owner_id (if missing)."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "campaigns" not in tables:
        # Fresh database — create the full table including owner_id.
        op.create_table(
            "campaigns",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("owner_id", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("data", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_campaigns_owner_id", "campaigns", ["owner_id"])
        op.create_index("ix_campaigns_status", "campaigns", ["status"])
    else:
        # Existing database — add owner_id only if it is missing.
        existing_columns = {c["name"] for c in inspector.get_columns("campaigns")}
        if "owner_id" not in existing_columns:
            op.add_column(
                "campaigns",
                sa.Column("owner_id", sa.String(), nullable=True),
            )
            op.create_index(
                "ix_campaigns_owner_id",
                "campaigns",
                ["owner_id"],
                unique=False,
            )


def downgrade() -> None:
    """Remove owner_id column and its index from the campaigns table."""
    op.drop_index("ix_campaigns_owner_id", table_name="campaigns")
    op.drop_column("campaigns", "owner_id")
