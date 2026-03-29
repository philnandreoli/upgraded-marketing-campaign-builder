"""Add A/B testing experiment tables

Revision ID: 0023
Revises: 0022
Create Date: 2026-03-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: Union[str, Sequence[str], None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_names(bind, table_name: str) -> set[str]:
    inspector = inspect(bind)
    try:
        return {idx["name"] for idx in inspector.get_indexes(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    """Create experiment tracking tables if they do not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "experiments" not in tables:
        op.create_table(
            "experiments",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "workspace_id",
                sa.String(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("variant_group", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("concluded_at", sa.DateTime(), nullable=True),
            sa.Column("winner_variant", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    experiment_indexes = _index_names(bind, "experiments")
    if "ix_experiments_campaign_id" not in experiment_indexes:
        op.create_index(
            "ix_experiments_campaign_id",
            "experiments",
            ["campaign_id"],
        )
    if "ix_experiments_workspace_id" not in experiment_indexes:
        op.create_index(
            "ix_experiments_workspace_id",
            "experiments",
            ["workspace_id"],
        )
    if "ix_experiments_campaign_group" not in experiment_indexes:
        op.create_index(
            "ix_experiments_campaign_group",
            "experiments",
            ["campaign_id", "variant_group"],
        )

    if "variant_metrics" not in tables:
        op.create_table(
            "variant_metrics",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "experiment_id",
                sa.String(),
                sa.ForeignKey("experiments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("content_piece_index", sa.Integer(), nullable=False),
            sa.Column("variant", sa.String(), nullable=False),
            sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("revenue", sa.Float(), nullable=False, server_default="0"),
            sa.Column("custom_metrics", sa.JSON(), nullable=False),
            sa.Column("source", sa.String(), nullable=False, server_default="manual"),
            sa.Column("recorded_at", sa.DateTime(), nullable=False),
        )

    metric_indexes = _index_names(bind, "variant_metrics")
    if "ix_variant_metrics_experiment_id" not in metric_indexes:
        op.create_index(
            "ix_variant_metrics_experiment_id",
            "variant_metrics",
            ["experiment_id"],
        )
    if "ix_variant_metrics_campaign_id" not in metric_indexes:
        op.create_index(
            "ix_variant_metrics_campaign_id",
            "variant_metrics",
            ["campaign_id"],
        )
    if "ix_variant_metrics_variant" not in metric_indexes:
        op.create_index(
            "ix_variant_metrics_variant",
            "variant_metrics",
            ["experiment_id", "variant"],
        )

    if "experiment_learnings" not in tables:
        op.create_table(
            "experiment_learnings",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "experiment_id",
                sa.String(),
                sa.ForeignKey("experiments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "campaign_id",
                sa.String(),
                sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "workspace_id",
                sa.String(),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("ai_generated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    learning_indexes = _index_names(bind, "experiment_learnings")
    if "ix_experiment_learnings_workspace_id" not in learning_indexes:
        op.create_index(
            "ix_experiment_learnings_workspace_id",
            "experiment_learnings",
            ["workspace_id"],
        )
    if "ix_experiment_learnings_campaign_id" not in learning_indexes:
        op.create_index(
            "ix_experiment_learnings_campaign_id",
            "experiment_learnings",
            ["campaign_id"],
        )
    if "ix_experiment_learnings_experiment_id" not in learning_indexes:
        op.create_index(
            "ix_experiment_learnings_experiment_id",
            "experiment_learnings",
            ["experiment_id"],
        )


def downgrade() -> None:
    """Drop A/B testing experiment tables."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "experiment_learnings" in tables:
        op.drop_table("experiment_learnings")
    if "variant_metrics" in tables:
        op.drop_table("variant_metrics")
    if "experiments" in tables:
        op.drop_table("experiments")
