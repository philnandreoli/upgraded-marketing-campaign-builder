"""Add user_settings table

Revision ID: 0014
Revises: 0013
Create Date: 2026-03-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_settings table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "user_settings" not in tables:
        op.create_table(
            "user_settings",
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("ui_theme", sa.String(), nullable=False, server_default="system"),
            sa.Column("locale", sa.String(), nullable=False, server_default="en-US"),
            sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
            sa.Column(
                "default_workspace_id",
                sa.String(),
                sa.ForeignKey("workspaces.id"),
                nullable=True,
            ),
            sa.Column("notification_prefs", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("dashboard_prefs", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "ui_theme IN ('light', 'dark', 'system')",
                name="ck_user_settings_ui_theme",
            ),
        )


def downgrade() -> None:
    """Drop user_settings table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "user_settings" in tables:
        op.drop_table("user_settings")
