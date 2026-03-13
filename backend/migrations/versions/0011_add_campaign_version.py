"""Add version column to campaigns table for optimistic locking

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-13 00:00:00.000000

Adds a non-nullable integer ``version`` column to the campaigns table.
All existing rows receive the default value of ``1``.  The column is used
for optimistic locking: every UPDATE increments the version and checks that
the caller's version still matches, preventing silent last-write-wins data
loss when concurrent processes update the same campaign document.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add version column to campaigns if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("campaigns")}

    if "version" not in existing_columns:
        op.add_column(
            "campaigns",
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )


def downgrade() -> None:
    """Remove version column from the campaigns table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("campaigns")}

    if "version" in existing_columns:
        op.drop_column("campaigns", "version")
