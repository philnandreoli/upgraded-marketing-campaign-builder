"""Add workspaces and workspace_members tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-07 00:00:00.000000

Creates the workspaces table and the workspace_members join table.
Both operations are idempotent — the table is only created if it does
not already exist.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the workspaces and workspace_members tables if they do not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "workspaces" not in tables:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column(
                "owner_id",
                sa.String(),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
            sa.Column("is_personal", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_workspaces_owner_id", "workspaces", ["owner_id"])

    if "workspace_members" not in tables:
        op.create_table(
            "workspace_members",
            sa.Column(
                "workspace_id",
                sa.String(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("added_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    """Drop the workspace_members and workspaces tables."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "workspace_members" in tables:
        op.drop_table("workspace_members")

    if "workspaces" in tables:
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("workspaces")}
        if "ix_workspaces_owner_id" in existing_indexes:
            op.drop_index("ix_workspaces_owner_id", table_name="workspaces")
        op.drop_table("workspaces")
