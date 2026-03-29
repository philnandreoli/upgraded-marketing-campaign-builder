"""PostgreSQL-backed persona store."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sa_delete, func, select

from backend.infrastructure.database import PersonaRow, WorkspaceMemberRow, WorkspaceRow, async_session
from backend.models.persona import Persona


class PersonaStore:
    """Repository for workspace personas."""

    async def create(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str,
        created_by: str,
        source_text: str = "",
    ) -> Persona:
        persona = Persona(
            workspace_id=workspace_id,
            name=name,
            description=description,
            source_text=source_text,
            created_by=created_by,
        )
        row = PersonaRow(
            id=persona.id,
            workspace_id=persona.workspace_id,
            name=persona.name,
            description=persona.description,
            source_text=persona.source_text,
            created_by=persona.created_by,
            created_at=persona.created_at,
            updated_at=persona.updated_at,
        )
        async with async_session() as session:
            session.add(row)
            await session.commit()
        return persona

    async def get(self, persona_id: str) -> Optional[Persona]:
        async with async_session() as session:
            row = await session.get(PersonaRow, persona_id)
            if row is None:
                return None
            return _row_to_model(row)

    async def list_by_workspace(
        self,
        workspace_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Persona], int]:
        async with async_session() as session:
            count_result = await session.execute(
                select(func.count())
                .select_from(PersonaRow)
                .where(PersonaRow.workspace_id == workspace_id)
            )
            total = count_result.scalar() or 0

            result = await session.execute(
                select(PersonaRow)
                .where(PersonaRow.workspace_id == workspace_id)
                .order_by(PersonaRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.scalars().all()
            return [_row_to_model(row) for row in rows], total

    async def update(
        self,
        persona_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Persona:
        async with async_session() as session:
            row = await session.get(PersonaRow, persona_id)
            if row is None:
                raise ValueError(f"Persona {persona_id!r} not found")
            if name is not None:
                row.name = name.strip()
            if description is not None:
                row.description = description.strip()
            row.updated_at = datetime.utcnow()
            await session.commit()
            return _row_to_model(row)

    async def delete(self, persona_id: str) -> bool:
        async with async_session() as session:
            result = await session.execute(
                sa_delete(PersonaRow).where(PersonaRow.id == persona_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def list_for_campaign(
        self,
        *,
        workspace_id: Optional[str],
        persona_ids: list[str],
    ) -> list[Persona]:
        if workspace_id is None or not persona_ids:
            return []
        unique_ids = list(dict.fromkeys(persona_ids))
        async with async_session() as session:
            result = await session.execute(
                select(PersonaRow)
                .where(PersonaRow.workspace_id == workspace_id)
                .where(PersonaRow.id.in_(unique_ids))
            )
            rows = result.scalars().all()

        by_id = {row.id: _row_to_model(row) for row in rows}
        return [by_id[pid] for pid in unique_ids if pid in by_id]

    async def is_workspace_member_or_admin(self, workspace_id: str, user_id: str) -> bool:
        async with async_session() as session:
            workspace = await session.get(WorkspaceRow, workspace_id)
            if workspace is None:
                return False
            membership = await session.get(WorkspaceMemberRow, (workspace_id, user_id))
            return membership is not None


def _row_to_model(row: PersonaRow) -> Persona:
    return Persona(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        source_text=row.source_text or "",
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


_persona_store: PersonaStore | None = None


def get_persona_store() -> PersonaStore:
    global _persona_store
    if _persona_store is None:
        _persona_store = PersonaStore()
    return _persona_store
