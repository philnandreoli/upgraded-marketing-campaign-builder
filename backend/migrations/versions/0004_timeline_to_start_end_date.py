"""Migrate brief.timeline to brief.start_date / brief.end_date

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-04 00:00:00.000000

For every row in the campaigns table, this migration reads the JSON
stored in the ``data`` column, removes ``brief.timeline``, and writes
back ``brief.start_date`` and ``brief.end_date`` (both set to null
because free-text timelines cannot be reliably parsed into ISO dates).
No DDL column changes are required — only the JSON payload is updated.
"""
from typing import Sequence, Union

import json

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace brief.timeline with brief.start_date / brief.end_date (null)."""
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, data FROM campaigns")).fetchall()
    for row_id, data_raw in rows:
        if not data_raw:
            continue
        try:
            data = json.loads(data_raw)
        except (json.JSONDecodeError, TypeError):
            continue

        brief = data.get("brief")
        if not isinstance(brief, dict):
            continue

        # Remove the old free-text field (if present)
        brief.pop("timeline", None)

        # Add structured date fields only when they are not already present
        brief.setdefault("start_date", None)
        brief.setdefault("end_date", None)

        bind.execute(
            sa.text("UPDATE campaigns SET data = :data WHERE id = :id"),
            {"data": json.dumps(data), "id": row_id},
        )


def downgrade() -> None:
    """Replace brief.start_date / brief.end_date with brief.timeline ("")."""
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, data FROM campaigns")).fetchall()
    for row_id, data_raw in rows:
        if not data_raw:
            continue
        try:
            data = json.loads(data_raw)
        except (json.JSONDecodeError, TypeError):
            continue

        brief = data.get("brief")
        if not isinstance(brief, dict):
            continue

        brief.pop("start_date", None)
        brief.pop("end_date", None)
        brief.setdefault("timeline", "")

        bind.execute(
            sa.text("UPDATE campaigns SET data = :data WHERE id = :id"),
            {"data": json.dumps(data), "id": row_id},
        )
