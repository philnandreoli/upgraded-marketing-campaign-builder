"""
PostgreSQL-backed workflow checkpoint store.

Provides upsert / fetch / delete for WorkflowCheckpoint rows so that
the coordinator's pipeline state survives server restarts.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sa_delete

from backend.models.workflow import WorkflowCheckpoint, WorkflowWaitType
from backend.services.database import WorkflowCheckpointRow, async_session


class WorkflowCheckpointStore:
    """Repository for WorkflowCheckpoint records backed by PostgreSQL."""

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        """Upsert *checkpoint* keyed by ``campaign_id``."""
        async with async_session() as session:
            row = await session.get(WorkflowCheckpointRow, checkpoint.campaign_id)
            if row is None:
                row = WorkflowCheckpointRow(
                    campaign_id=checkpoint.campaign_id,
                    current_stage=checkpoint.current_stage,
                    wait_type=checkpoint.wait_type.value if checkpoint.wait_type else None,
                    revision_cycle=checkpoint.revision_cycle,
                    resume_token=checkpoint.resume_token,
                    context=json.dumps(checkpoint.context),
                    created_at=checkpoint.created_at,
                    updated_at=checkpoint.updated_at,
                )
                session.add(row)
            else:
                row.current_stage = checkpoint.current_stage
                row.wait_type = checkpoint.wait_type.value if checkpoint.wait_type else None
                row.revision_cycle = checkpoint.revision_cycle
                row.resume_token = checkpoint.resume_token
                row.context = json.dumps(checkpoint.context)
                row.updated_at = checkpoint.updated_at
            await session.commit()

    async def get_checkpoint(self, campaign_id: str) -> Optional[WorkflowCheckpoint]:
        """Return the checkpoint for *campaign_id*, or ``None`` if not found."""
        async with async_session() as session:
            row = await session.get(WorkflowCheckpointRow, campaign_id)
            if row is None:
                return None
            return WorkflowCheckpoint(
                campaign_id=row.campaign_id,
                current_stage=row.current_stage,
                wait_type=WorkflowWaitType(row.wait_type) if row.wait_type else None,
                revision_cycle=row.revision_cycle,
                resume_token=row.resume_token,
                context=json.loads(row.context) if row.context else {},
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    async def delete_checkpoint(self, campaign_id: str) -> bool:
        """Delete the checkpoint for *campaign_id*.

        Returns ``True`` if a row was deleted, ``False`` if not found.
        """
        async with async_session() as session:
            result = await session.execute(
                sa_delete(WorkflowCheckpointRow).where(
                    WorkflowCheckpointRow.campaign_id == campaign_id
                )
            )
            await session.commit()
            return result.rowcount > 0


# Module-level singleton
_checkpoint_store: WorkflowCheckpointStore | None = None


def get_workflow_checkpoint_store() -> WorkflowCheckpointStore:
    global _checkpoint_store
    if _checkpoint_store is None:
        _checkpoint_store = WorkflowCheckpointStore()
    return _checkpoint_store
