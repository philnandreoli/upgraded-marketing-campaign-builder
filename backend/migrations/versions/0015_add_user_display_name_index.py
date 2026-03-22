"""Add index on users.display_name for admin search

Revision ID: 0015
Revises: 0014
Create Date: 2026-03-22 00:00:00.000000

The admin user-search endpoint now filters on display_name in SQL via an
ilike query. Adding a plain B-tree index on users.display_name lets the
planner use an index scan for prefix/substring searches on databases that
support index-accelerated LIKE (e.g. via pg_trgm on PostgreSQL) and
keeps the column indexed for equality look-ups in all cases.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create index on users.display_name."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes("users")}
    if "ix_users_display_name" not in existing:
        op.create_index("ix_users_display_name", "users", ["display_name"])


def downgrade() -> None:
    """Drop index on users.display_name."""
    op.drop_index("ix_users_display_name", table_name="users")
