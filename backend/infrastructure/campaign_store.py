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

from sqlalchemy import delete as sa_delete, or_, select

from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import CampaignMember, CampaignMemberRole, User, UserRole
from backend.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from backend.infrastructure.database import (
    CampaignMemberRow,
    CampaignRow,
    UserRow,
    WorkspaceMemberRow,
    WorkspaceRow,
    async_session,
)


class CampaignStore:
    """Campaign repository backed by PostgreSQL."""

    # ------------------------------------------------------------------
    # Campaign CRUD — all async
    # ------------------------------------------------------------------

    async def create(
        self,
        brief: CampaignBrief,
        owner_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Campaign:
        """Create a new campaign from a brief and persist it.

        When *owner_id* is provided, the creating user is automatically added
        as an *owner* member in the campaign_members table.  When *workspace_id*
        is provided, the campaign is associated with that workspace.
        """
        campaign = Campaign(brief=brief, owner_id=owner_id, workspace_id=workspace_id)
        row = CampaignRow(
            id=campaign.id,
            owner_id=campaign.owner_id,
            workspace_id=campaign.workspace_id,
            status=campaign.status.value,
            data=campaign.model_dump_json(),
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
        )
        async with async_session() as session:
            session.add(row)
            # Flush the campaign row first so it exists in the DB before
            # inserting the campaign_members row (FK constraint).
            await session.flush()
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
                    workspace_id=campaign.workspace_id,
                    status=campaign.status.value,
                    data=campaign.model_dump_json(),
                    created_at=campaign.created_at,
                    updated_at=campaign.updated_at,
                )
                session.add(row)
            else:
                row.status = campaign.status.value
                row.workspace_id = campaign.workspace_id
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

        Admins see every campaign.  Other users see campaigns where they
        appear in the campaign_members table (any role) *or* where they are
        a member of the campaign's workspace.
        """
        async with async_session() as session:
            if is_admin:
                result = await session.execute(
                    select(CampaignRow).order_by(CampaignRow.created_at.desc())
                )
            else:
                result = await session.execute(
                    select(CampaignRow)
                    .outerjoin(CampaignMemberRow, CampaignRow.id == CampaignMemberRow.campaign_id)
                    .outerjoin(
                        WorkspaceMemberRow,
                        CampaignRow.workspace_id == WorkspaceMemberRow.workspace_id,
                    )
                    .where(
                        or_(
                            CampaignMemberRow.user_id == user_id,
                            WorkspaceMemberRow.user_id == user_id,
                        )
                    )
                    .distinct()
                    .order_by(CampaignRow.created_at.desc())
                )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows]

    async def move_campaign(self, campaign_id: str, workspace_id: Optional[str]) -> Campaign:
        """Move a campaign to a different workspace (or orphan it when *workspace_id* is ``None``).

        Updates both the indexed column on ``campaigns`` and the JSON document.
        Admin-only enforcement is expected at the API layer.
        """
        async with async_session() as session:
            row = await session.get(CampaignRow, campaign_id)
            if row is None:
                raise ValueError(f"Campaign {campaign_id!r} not found")
            campaign = Campaign.model_validate_json(row.data)
            campaign.workspace_id = workspace_id
            campaign.updated_at = datetime.utcnow()
            row.workspace_id = workspace_id
            row.data = campaign.model_dump_json()
            row.updated_at = campaign.updated_at
            await session.commit()
        return campaign

    # ------------------------------------------------------------------
    # Campaign membership
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # User helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Workspace CRUD
    # ------------------------------------------------------------------

    async def create_workspace(
        self,
        name: str,
        owner_id: str,
        description: Optional[str] = None,
        is_personal: bool = False,
    ) -> Workspace:
        """Create a new workspace and add the owner as a CREATOR member."""
        workspace = Workspace(
            name=name,
            owner_id=owner_id,
            description=description,
            is_personal=is_personal,
        )
        now = datetime.utcnow()
        row = WorkspaceRow(
            id=workspace.id,
            name=workspace.name,
            description=workspace.description,
            owner_id=workspace.owner_id,
            is_personal=workspace.is_personal,
            created_at=now,
            updated_at=now,
        )
        async with async_session() as session:
            session.add(row)
            await session.flush()
            member_row = WorkspaceMemberRow(
                workspace_id=workspace.id,
                user_id=owner_id,
                role=WorkspaceRole.CREATOR.value,
                added_at=now,
            )
            session.add(member_row)
            await session.commit()
        return workspace

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Return the Workspace for *workspace_id*, or ``None`` if not found."""
        async with async_session() as session:
            row = await session.get(WorkspaceRow, workspace_id)
            if row is None:
                return None
            return self._workspace_from_row(row)

    async def update_workspace(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Workspace:
        """Update mutable fields on a workspace and return the updated model.

        Raises ``ValueError`` if the workspace does not exist.
        """
        async with async_session() as session:
            row = await session.get(WorkspaceRow, workspace_id)
            if row is None:
                raise ValueError(f"Workspace {workspace_id!r} not found")
            if name is not None:
                row.name = name
            if description is not None:
                row.description = description
            row.updated_at = datetime.utcnow()
            await session.commit()
            return self._workspace_from_row(row)

    async def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace, orphaning its campaigns (sets workspace_id = NULL).

        Returns ``True`` if the workspace existed and was deleted, ``False`` otherwise.
        """
        async with async_session() as session:
            row = await session.get(WorkspaceRow, workspace_id)
            if row is None:
                return False
            # Orphan campaigns — update both the indexed column and the JSON document
            # in a single transaction so they stay in sync.
            result = await session.execute(
                select(CampaignRow).where(CampaignRow.workspace_id == workspace_id)
            )
            for campaign_row in result.scalars().all():
                try:
                    campaign = Campaign.model_validate_json(campaign_row.data)
                    campaign.workspace_id = None
                    campaign_row.data = campaign.model_dump_json()
                except Exception:
                    pass
                campaign_row.workspace_id = None
            await session.delete(row)
            await session.commit()
        return True

    async def list_workspaces(self, user_id: str, is_admin: bool = False) -> list[Workspace]:
        """Return workspaces visible to *user_id*.

        Admins see all workspaces; other users see only workspaces they are
        a member of.
        """
        async with async_session() as session:
            if is_admin:
                result = await session.execute(
                    select(WorkspaceRow).order_by(WorkspaceRow.created_at.desc())
                )
            else:
                result = await session.execute(
                    select(WorkspaceRow)
                    .join(
                        WorkspaceMemberRow,
                        WorkspaceRow.id == WorkspaceMemberRow.workspace_id,
                    )
                    .where(WorkspaceMemberRow.user_id == user_id)
                    .order_by(WorkspaceRow.created_at.desc())
                )
            rows = result.scalars().all()
            return [self._workspace_from_row(r) for r in rows]

    async def list_workspace_campaigns(self, workspace_id: str) -> list[Campaign]:
        """Return all campaigns that belong to *workspace_id*."""
        async with async_session() as session:
            result = await session.execute(
                select(CampaignRow)
                .where(CampaignRow.workspace_id == workspace_id)
                .order_by(CampaignRow.created_at.desc())
            )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows]

    async def get_personal_workspace(self, user_id: str) -> Optional[Workspace]:
        """Return the personal workspace for *user_id*, or ``None`` if not found."""
        async with async_session() as session:
            result = await session.execute(
                select(WorkspaceRow)
                .where(WorkspaceRow.owner_id == user_id)
                .where(WorkspaceRow.is_personal.is_(True))
            )
            row = result.scalars().first()
            if row is None:
                return None
            return self._workspace_from_row(row)

    # ------------------------------------------------------------------
    # Workspace membership
    # ------------------------------------------------------------------

    async def get_workspace_member_role(
        self, workspace_id: str, user_id: str
    ) -> Optional[WorkspaceRole]:
        """Return the workspace role for *user_id*, or ``None`` if not a member."""
        async with async_session() as session:
            row = await session.get(WorkspaceMemberRow, (workspace_id, user_id))
            if row is None:
                return None
            return WorkspaceRole(row.role)

    async def add_workspace_member(
        self, workspace_id: str, user_id: str, role: WorkspaceRole
    ) -> None:
        """Add *user_id* to *workspace_id* with *role*.

        If the user is already a member the existing row is updated.
        """
        async with async_session() as session:
            existing = await session.get(WorkspaceMemberRow, (workspace_id, user_id))
            if existing is not None:
                existing.role = role.value
            else:
                session.add(
                    WorkspaceMemberRow(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role=role.value,
                        added_at=datetime.utcnow(),
                    )
                )
            await session.commit()

    async def remove_workspace_member(self, workspace_id: str, user_id: str) -> bool:
        """Remove *user_id* from *workspace_id*.

        Returns ``True`` if a row was deleted, ``False`` if not found.
        """
        async with async_session() as session:
            result = await session.execute(
                sa_delete(WorkspaceMemberRow).where(
                    WorkspaceMemberRow.workspace_id == workspace_id,
                    WorkspaceMemberRow.user_id == user_id,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def update_workspace_member_role(
        self, workspace_id: str, user_id: str, role: WorkspaceRole
    ) -> None:
        """Update the role for *user_id* in *workspace_id*.

        Raises ``ValueError`` if the membership does not exist.
        """
        async with async_session() as session:
            row = await session.get(WorkspaceMemberRow, (workspace_id, user_id))
            if row is None:
                raise ValueError(
                    f"User {user_id!r} is not a member of workspace {workspace_id!r}"
                )
            row.role = role.value
            await session.commit()

    async def list_workspace_members(self, workspace_id: str) -> list[WorkspaceMember]:
        """Return all members of *workspace_id*."""
        async with async_session() as session:
            result = await session.execute(
                select(WorkspaceMemberRow).where(
                    WorkspaceMemberRow.workspace_id == workspace_id
                )
            )
            rows = result.scalars().all()
            return [
                WorkspaceMember(
                    workspace_id=row.workspace_id,
                    user_id=row.user_id,
                    role=WorkspaceRole(row.role),
                    added_at=row.added_at,
                )
                for row in rows
            ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _workspace_from_row(row: WorkspaceRow) -> Workspace:
        return Workspace(
            id=row.id,
            name=row.name,
            description=row.description,
            owner_id=row.owner_id,
            is_personal=row.is_personal,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# Module-level singleton
_store: CampaignStore | None = None


def get_campaign_store() -> CampaignStore:
    global _store
    if _store is None:
        _store = CampaignStore()
    return _store
