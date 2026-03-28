"""Add personas table

Revision ID: 0020
Revises: 0019
Create Date: 2026-03-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: Union[str, Sequence[str], None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "personas",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personas_workspace_id", "personas", ["workspace_id"], unique=False)
    op.create_index("ix_personas_workspace_created", "personas", ["workspace_id", "created_at"], unique=False)
    op.create_index("ix_personas_workspace_name", "personas", ["workspace_id", "name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_personas_workspace_name", table_name="personas")
    op.drop_index("ix_personas_workspace_created", table_name="personas")
    op.drop_index("ix_personas_workspace_id", table_name="personas")
    op.drop_table("personas")
