"""Add image_assets table

Revision ID: 0016
Revises: 0015
Create Date: 2026-03-22 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create image_assets table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "image_assets" not in tables:
        op.create_table(
            "image_assets",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=False),
            sa.Column("content_piece_index", sa.Integer(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("image_url", sa.Text(), nullable=True),
            sa.Column("storage_path", sa.Text(), nullable=True),
            sa.Column("dimensions", sa.String(), nullable=False, server_default="1024x1024"),
            sa.Column("format", sa.String(), nullable=False, server_default="png"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("image_assets")}
    if "ix_image_assets_campaign_id" not in indexes:
        op.create_index("ix_image_assets_campaign_id", "image_assets", ["campaign_id"])


def downgrade() -> None:
    """Drop image_assets table."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "image_assets" in tables:
        op.drop_table("image_assets")
