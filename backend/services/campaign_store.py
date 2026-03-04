"""
PostgreSQL-backed campaign store.

Persists campaigns as JSON documents in a single 'campaigns' table.
The public API is intentionally synchronous-looking — each method runs
a short async DB call via the shared session factory.  Because FastAPI
route handlers and background tasks are already async, the callers can
simply ``await`` these methods.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import delete as sa_delete, select

from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import CampaignMember, CampaignMemberRole, User, UserRole
from backend.services.database import CampaignMemberRow, CampaignRow, UserRow, async_session


class CampaignStore:
    """Campaign repository backed by PostgreSQL."""

    # ------------------------------------------------------------------
    # CRUD — all async
    # ------------------------------------------------------------------

    async def create(self, brief: CampaignBrief, owner_id: Optional[str] = None) -> Campaign:
        """Create a new campaign from a brief and persist it.

        When *owner_id* is provided, the creating user is automatically added
        as an *owner* member in the campaign_members table.
        """
        campaign = Campaign(brief=brief, owner_id=owner_id)
        row = CampaignRow(
            id=campaign.id,
            owner_id=campaign.owner_id,
            status=campaign.status.value,
            data=campaign.model_dump_json(),
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
        )
        async with async_session() as session:
            session.add(row)
            if owner_id is not None:
                member_row = CampaignMemberRow(
                    campaign_id=campaign.id,
                    user_id=owner_id,
                    role=CampaignMemberRole.OWNER.value,
                    added_at=datetime.utcnow(),
                )
                session.add(member_row)
            await session.commit()
        return campaign

    async def get(self, campaign_id: str) -> Optional[Campaign]:
        async with async_session() as session:
            row = await session.get(CampaignRow, campaign_id)
            if row is None:
                return None
            return Campaign.model_validate_json(row.data)

    async def update(self, campaign: Campaign) -> Campaign:
        async with async_session() as session:
            row = await session.get(CampaignRow, campaign.id)
            if row is None:
                # First time persisting — insert instead
                row = CampaignRow(
                    id=campaign.id,
                    owner_id=campaign.owner_id,
                    status=campaign.status.value,
                    data=campaign.model_dump_json(),
                    created_at=campaign.created_at,
                    updated_at=campaign.updated_at,
                )
                session.add(row)
            else:
                row.status = campaign.status.value
                row.data = campaign.model_dump_json()
                row.updated_at = campaign.updated_at
            await session.commit()
        return campaign

    async def list_all(self) -> list[Campaign]:
        async with async_session() as session:
            result = await session.execute(
                select(CampaignRow).order_by(CampaignRow.created_at.desc())
            )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows]

    async def list_by_owner(self, owner_id: str) -> list[Campaign]:
        """Return all campaigns belonging to a specific owner."""
        async with async_session() as session:
            result = await session.execute(
                select(CampaignRow)
                .where(CampaignRow.owner_id == owner_id)
                .order_by(CampaignRow.created_at.desc())
            )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows]

    async def list_accessible(self, user_id: str, is_admin: bool = False) -> list[Campaign]:
        """Return all campaigns accessible to *user_id*.

        Admins see every campaign.  Other users see only campaigns where they
        appear in the campaign_members table (any role).
        """
        async with async_session() as session:
            if is_admin:
                result = await session.execute(
                    select(CampaignRow).order_by(CampaignRow.created_at.desc())
                )
            else:
                result = await session.execute(
                    select(CampaignRow)
                    .join(CampaignMemberRow, CampaignRow.id == CampaignMemberRow.campaign_id)
                    .where(CampaignMemberRow.user_id == user_id)
                    .order_by(CampaignRow.created_at.desc())
                )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows]

    async def get_member_role(self, campaign_id: str, user_id: str) -> Optional[CampaignMemberRole]:
        """Return the membership role for *user_id* in *campaign_id*, or ``None`` if not a member."""
        async with async_session() as session:
            row = await session.get(CampaignMemberRow, (campaign_id, user_id))
            if row is None:
                return None
            return CampaignMemberRole(row.role)

    async def get_member(self, campaign_id: str, user_id: str) -> Optional[CampaignMember]:
        """Return the full CampaignMember for *user_id* in *campaign_id*, or ``None`` if not a member."""
        async with async_session() as session:
            row = await session.get(CampaignMemberRow, (campaign_id, user_id))
            if row is None:
                return None
            return CampaignMember(
                campaign_id=row.campaign_id,
                user_id=row.user_id,
                role=CampaignMemberRole(row.role),
                added_at=row.added_at,
            )

    async def add_member(
        self,
        campaign_id: str,
        user_id: str,
        role: CampaignMemberRole = CampaignMemberRole.VIEWER,
    ) -> None:
        """Add *user_id* to *campaign_id* with the given per-campaign *role*.

        If the user is already a member the existing row is updated.
        """
        async with async_session() as session:
            existing = await session.get(CampaignMemberRow, (campaign_id, user_id))
            if existing is not None:
                existing.role = role.value
            else:
                member_row = CampaignMemberRow(
                    campaign_id=campaign_id,
                    user_id=user_id,
                    role=role.value,
                    added_at=datetime.utcnow(),
                )
                session.add(member_row)
            await session.commit()

    async def remove_member(self, campaign_id: str, user_id: str) -> bool:
        """Remove *user_id* from *campaign_id*.

        Returns ``True`` if a row was deleted, ``False`` if not found.
        """
        async with async_session() as session:
            result = await session.execute(
                sa_delete(CampaignMemberRow).where(
                    CampaignMemberRow.campaign_id == campaign_id,
                    CampaignMemberRow.user_id == user_id,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def list_members(self, campaign_id: str) -> list[CampaignMember]:
        """Return all members of *campaign_id*."""
        async with async_session() as session:
            result = await session.execute(
                select(CampaignMemberRow).where(CampaignMemberRow.campaign_id == campaign_id)
            )
            rows = result.scalars().all()
            return [
                CampaignMember(
                    campaign_id=row.campaign_id,
                    user_id=row.user_id,
                    role=CampaignMemberRole(row.role),
                    added_at=row.added_at,
                )
                for row in rows
            ]

    async def get_user(self, user_id: str) -> Optional[User]:
        """Return the User for *user_id*, or ``None`` if not found."""
        async with async_session() as session:
            row = await session.get(UserRow, user_id)
            if row is None:
                return None
            return User(
                id=row.id,
                email=row.email,
                display_name=row.display_name,
                role=UserRole(row.role),
                created_at=row.created_at,
                updated_at=row.updated_at,
                is_active=row.is_active,
            )

    async def delete(self, campaign_id: str) -> bool:
        async with async_session() as session:
            result = await session.execute(
                sa_delete(CampaignRow).where(CampaignRow.id == campaign_id)
            )
            await session.commit()
            return result.rowcount > 0


# Module-level singleton
_store: CampaignStore | None = None


def get_campaign_store() -> CampaignStore:
    global _store
    if _store is None:
        _store = CampaignStore()
    return _store
