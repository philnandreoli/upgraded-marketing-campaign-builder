"""
PostgreSQL-backed workflow signal store.

Human-input signals (clarification responses, content approvals) are written
here by API handlers and polled by coordinator wait gates.  This decouples the
coordinator from the API process, enabling cross-process execution.

Signal lifecycle:
  1. API handler calls ``write_signal`` → inserts a row with ``consumed_at=None``.
  2. Coordinator gate calls ``poll_signal`` → returns the oldest unconsumed row.
  3. Coordinator gate calls ``consume_signal`` → sets ``consumed_at`` so the row
     is not returned again on subsequent polls.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy import update as sa_update

from backend.services.database import WorkflowSignalRow, async_session


# String constants for signal_type values.
class SignalType:
    CLARIFICATION_RESPONSE = "clarification_response"
    CONTENT_APPROVAL = "content_approval"


class WorkflowSignalStore:
    """Repository for ``WorkflowSignalRow`` records backed by PostgreSQL."""

    async def write_signal(
        self, campaign_id: str, signal_type: str, payload: dict
    ) -> str:
        """Insert a new signal row and return its UUID string ID."""
        signal_id = str(uuid.uuid4())
        row = WorkflowSignalRow(
            id=signal_id,
            campaign_id=campaign_id,
            signal_type=signal_type,
            payload=json.dumps(payload),
            created_at=datetime.utcnow(),
            consumed_at=None,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return signal_id

    async def poll_signal(
        self, campaign_id: str, signal_type: str
    ) -> Optional[dict]:
        """Return the oldest unconsumed signal for the given campaign and type.

        Returns a dict with ``id`` and ``payload`` (already deserialized), or
        ``None`` if no pending signal exists.
        """
        async with async_session() as session:
            stmt = (
                select(WorkflowSignalRow)
                .where(
                    WorkflowSignalRow.campaign_id == campaign_id,
                    WorkflowSignalRow.signal_type == signal_type,
                    WorkflowSignalRow.consumed_at.is_(None),
                )
                .order_by(WorkflowSignalRow.created_at)
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": row.id,
                "payload": json.loads(row.payload),
            }

    async def consume_signal(self, signal_id: str) -> None:
        """Mark a signal as consumed by setting ``consumed_at``."""
        async with async_session() as session:
            await session.execute(
                sa_update(WorkflowSignalRow)
                .where(WorkflowSignalRow.id == signal_id)
                .values(consumed_at=datetime.utcnow())
            )
            await session.commit()


# Module-level singleton
_signal_store: WorkflowSignalStore | None = None


def get_workflow_signal_store() -> WorkflowSignalStore:
    global _signal_store
    if _signal_store is None:
        _signal_store = WorkflowSignalStore()
    return _signal_store
