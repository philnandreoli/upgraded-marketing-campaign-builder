"""Add event_overflow table

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-07 00:00:00.000000

Creates the event_overflow table used by PostgresEventPublisher to store
event payloads that exceed the 8 KB PostgreSQL NOTIFY payload limit.

When an event payload is too large, the publisher writes the full payload
here and sends only the overflow_id reference via NOTIFY.  The EventSubscriber
reads the full payload from this table before broadcasting to WebSocket clients.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the event_overflow table if it does not already exist."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "event_overflow" not in tables:
        op.create_table(
            "event_overflow",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("channel", sa.String(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_event_overflow_channel",
            "event_overflow",
            ["channel"],
        )


def downgrade() -> None:
    """Drop the event_overflow table."""
    op.drop_index("ix_event_overflow_channel", table_name="event_overflow")
    op.drop_table("event_overflow")
