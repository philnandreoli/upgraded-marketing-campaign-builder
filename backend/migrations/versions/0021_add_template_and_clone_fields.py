"""Add template and clone fields to campaigns table

Revision ID: 0022
Revises: 0021
Create Date: 2026-03-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: Union[str, Sequence[str], None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column(
            "is_template",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("campaigns", sa.Column("template_category", sa.String(), nullable=True))
    op.add_column("campaigns", sa.Column("template_tags", sa.JSON(), nullable=True))
    op.add_column("campaigns", sa.Column("template_description", sa.Text(), nullable=True))
    op.add_column(
        "campaigns",
        sa.Column(
            "template_visibility",
            sa.String(),
            nullable=True,
            server_default="workspace",
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "template_featured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "campaigns",
        sa.Column(
            "template_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column("campaigns", sa.Column("template_parameters", sa.JSON(), nullable=True))
    op.add_column("campaigns", sa.Column("cloned_from_campaign_id", sa.String(), nullable=True))
    op.add_column("campaigns", sa.Column("cloned_from_template_version", sa.Integer(), nullable=True))
    op.add_column("campaigns", sa.Column("clone_depth", sa.String(), nullable=True))

    op.create_foreign_key(
        "fk_campaigns_cloned_from_campaign_id_campaigns",
        "campaigns",
        "campaigns",
        ["cloned_from_campaign_id"],
        ["id"],
    )

    op.create_index("ix_campaigns_is_template", "campaigns", ["is_template"], unique=False)
    op.create_index("ix_campaigns_template_visibility", "campaigns", ["template_visibility"], unique=False)
    op.create_index("ix_campaigns_template_category", "campaigns", ["template_category"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_campaigns_template_category", table_name="campaigns")
    op.drop_index("ix_campaigns_template_visibility", table_name="campaigns")
    op.drop_index("ix_campaigns_is_template", table_name="campaigns")
    op.drop_constraint("fk_campaigns_cloned_from_campaign_id_campaigns", "campaigns", type_="foreignkey")

    op.drop_column("campaigns", "clone_depth")
    op.drop_column("campaigns", "cloned_from_template_version")
    op.drop_column("campaigns", "cloned_from_campaign_id")
    op.drop_column("campaigns", "template_parameters")
    op.drop_column("campaigns", "template_version")
    op.drop_column("campaigns", "template_featured")
    op.drop_column("campaigns", "template_visibility")
    op.drop_column("campaigns", "template_description")
    op.drop_column("campaigns", "template_tags")
    op.drop_column("campaigns", "template_category")
    op.drop_column("campaigns", "is_template")
