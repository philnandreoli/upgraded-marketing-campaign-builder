"""
PostgreSQL-backed campaign store.

Persists campaigns as JSON documents in a single 'campaigns' table.
The public API is intentionally synchronous-looking — each method runs
a short async DB call via the shared session factory.  Because FastAPI
route handlers and background tasks are already async, the callers can
simply ``await`` these methods.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON as SA_JSON, case, delete as sa_delete, exists, func, or_, select, update as sa_update

from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus
from backend.models.user import CampaignMember, CampaignMemberRole, User, UserRole, roles_from_db
from backend.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from backend.core.exceptions import ConcurrentUpdateError
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
            version=campaign.version,
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
            campaign = Campaign.model_validate_json(row.data)
            campaign.version = row.version
            return campaign

    async def update(self, campaign: Campaign) -> Campaign:
        """Persist a campaign using optimistic locking.

        Performs a conditional UPDATE: ``WHERE id = :id AND version = :version``.
        If zero rows are affected the campaign was concurrently modified; a
        ``ConcurrentUpdateError`` is raised so callers can reload and retry.

        If no row exists at all (first-time persist), an INSERT is performed
        instead and the version stays at its current value.
        """
        async with async_session() as session:
            result = await session.execute(
                sa_update(CampaignRow)
                .where(
                    CampaignRow.id == campaign.id,
                    CampaignRow.version == campaign.version,
                )
                .values(
                    status=campaign.status.value,
                    workspace_id=campaign.workspace_id,
                    data=campaign.model_dump_json(),
                    updated_at=campaign.updated_at,
                    version=campaign.version + 1,
                )
            )
            if result.rowcount == 0:
                # Either no row exists yet (first save) or a concurrent writer
                # already bumped the version.  Check which case it is.
                existing = await session.get(CampaignRow, campaign.id)
                if existing is None:
                    # First time persisting — insert instead
                    row = CampaignRow(
                        id=campaign.id,
                        owner_id=campaign.owner_id,
                        workspace_id=campaign.workspace_id,
                        status=campaign.status.value,
                        data=campaign.model_dump_json(),
                        created_at=campaign.created_at,
                        updated_at=campaign.updated_at,
                        version=campaign.version,
                    )
                    session.add(row)
                else:
                    raise ConcurrentUpdateError(
                        f"Campaign {campaign.id} was modified by another process "
                        f"(expected version {campaign.version}, "
                        f"found {existing.version})"
                    )
            else:
                campaign.version += 1
            await session.commit()
        return campaign

    async def list_all(self) -> list[Campaign]:
        async with async_session() as session:
            result = await session.execute(
                select(CampaignRow).order_by(CampaignRow.created_at.desc())
            )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows]

    async def list_all_paginated(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return paginated campaign summaries without full JSON deserialization.

        Projects only the indexed columns plus ``brief.product_or_service`` and
        ``brief.goal`` via PostgreSQL JSON path extraction.  This avoids loading
        the ~50–200 KB full JSON document for every campaign when only summary
        data is needed (e.g. the admin dashboard).

        Returns a ``(items, total)`` tuple where each item is a plain dict with
        the summary fields.
        """
        async with async_session() as session:
            count_result = await session.execute(
                select(func.count()).select_from(CampaignRow)
            )
            total = count_result.scalar() or 0

            result = await session.execute(
                select(
                    CampaignRow.id,
                    CampaignRow.status,
                    CampaignRow.owner_id,
                    CampaignRow.workspace_id,
                    CampaignRow.created_at,
                    CampaignRow.updated_at,
                    func.json_extract_path_text(
                        CampaignRow.data.cast(SA_JSON), "brief", "product_or_service"
                    ).label("product_or_service"),
                    func.json_extract_path_text(
                        CampaignRow.data.cast(SA_JSON), "brief", "goal"
                    ).label("goal"),
                )
                .order_by(CampaignRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.all()
            return [
                {
                    "id": r.id,
                    "status": r.status,
                    "owner_id": r.owner_id,
                    "workspace_id": r.workspace_id,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "product_or_service": r.product_or_service,
                    "goal": r.goal,
                }
                for r in rows
            ], total

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

    async def list_by_status(self, statuses: list[CampaignStatus]) -> list[Campaign]:
        """Return all campaigns whose status is in *statuses*."""
        status_values = [s.value for s in statuses]
        async with async_session() as session:
            result = await session.execute(
                select(CampaignRow)
                .where(CampaignRow.status.in_(status_values))
                .order_by(CampaignRow.created_at.desc())
            )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows]

    async def list_accessible(
        self,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Campaign], int]:
        """Return paginated campaigns accessible to *user_id*.

        Admins (determined by looking up the user's actual platform role in the
        database) see every campaign.  Other users see campaigns where they
        appear in the campaign_members table (any role) *or* where they are
        a member of the campaign's workspace.

        Returns a ``(campaigns, total)`` tuple.
        """
        async with async_session() as session:
            # Determine admin status from the database — do not trust a caller-supplied flag.
            user_row = await session.get(UserRow, user_id)
            is_admin = user_row is not None and UserRole.ADMIN in roles_from_db(user_row.role)
            if is_admin:
                base = select(CampaignRow)
            else:
                # Use EXISTS subqueries instead of OUTERJOIN + DISTINCT to avoid
                # row-multiplication when campaigns have multiple members/workspace members.
                campaign_member_subq = (
                    select(CampaignMemberRow.campaign_id)
                    .where(
                        CampaignMemberRow.campaign_id == CampaignRow.id,
                        CampaignMemberRow.user_id == user_id,
                    )
                    .correlate(CampaignRow)
                )
                workspace_member_subq = (
                    select(WorkspaceMemberRow.workspace_id)
                    .where(
                        WorkspaceMemberRow.workspace_id == CampaignRow.workspace_id,
                        WorkspaceMemberRow.user_id == user_id,
                    )
                    .correlate(CampaignRow)
                )
                base = (
                    select(CampaignRow)
                    .where(
                        or_(
                            exists(campaign_member_subq),
                            exists(workspace_member_subq),
                        )
                    )
                )

            # Total count
            count_result = await session.execute(
                select(func.count()).select_from(base.subquery())
            )
            total = count_result.scalar()

            # Paginated rows
            result = await session.execute(
                base.order_by(CampaignRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows], total

    async def move_campaign(
        self,
        campaign_id: str,
        workspace_id: Optional[str],
        *,
        acting_user_id: Optional[str] = None,
    ) -> Campaign:
        """Move a campaign to a different workspace (or orphan it when *workspace_id* is ``None``).

        Updates both the indexed column on ``campaigns`` and the JSON document.

        When *acting_user_id* is provided the caller's platform role is looked up
        from the database and a ``PermissionError`` is raised unless the user holds
        the ``admin`` platform role.
        """
        async with async_session() as session:
            if acting_user_id is not None:
                user_row = await session.get(UserRow, acting_user_id)
                if user_row is None or UserRole.ADMIN not in roles_from_db(user_row.role):
                    raise PermissionError("Admin access required to move campaigns")
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
                roles=roles_from_db(row.role),
                created_at=row.created_at,
                updated_at=row.updated_at,
                is_active=row.is_active,
            )

    async def delete(self, campaign_id: str, *, acting_user_id: Optional[str] = None) -> bool:
        """Delete a campaign by ID.

        When *acting_user_id* is provided the caller's campaign membership is
        verified and a ``PermissionError`` is raised unless the user holds the
        ``owner`` role for this campaign.
        """
        async with async_session() as session:
            if acting_user_id is not None:
                member_row = await session.get(CampaignMemberRow, (campaign_id, acting_user_id))
                if member_row is None or member_row.role != CampaignMemberRole.OWNER.value:
                    raise PermissionError("User does not have delete permission")
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

    async def delete_workspace(
        self,
        workspace_id: str,
        *,
        acting_user_id: Optional[str] = None,
    ) -> bool:
        """Delete a workspace, orphaning its campaigns (sets workspace_id = NULL).

        When *acting_user_id* is provided the caller must be either a platform
        admin or the ``creator`` member of this workspace.  A ``PermissionError``
        is raised if neither condition is met.

        Returns ``True`` if the workspace existed and was deleted, ``False`` otherwise.
        """
        async with async_session() as session:
            if acting_user_id is not None:
                user_row = await session.get(UserRow, acting_user_id)
                is_admin = user_row is not None and UserRole.ADMIN in roles_from_db(user_row.role)
                if not is_admin:
                    member_row = await session.get(
                        WorkspaceMemberRow, (workspace_id, acting_user_id)
                    )
                    if member_row is None or member_row.role != WorkspaceRole.CREATOR.value:
                        raise PermissionError(
                            "User does not have permission to delete this workspace"
                        )
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

    async def get_workspace_summaries(
        self,
        workspace_ids: list[str],
        *,
        user_id: Optional[str],
        is_admin: bool,
    ) -> dict[str, dict[str, Optional[str] | int]]:
        """Return aggregated summary metadata for the given workspaces.

        Returned mapping keys are workspace IDs. Each value includes:
        ``role`` (for *user_id*), ``member_count``, ``campaign_count``,
        and ``owner_display_name``.
        """
        if not workspace_ids:
            return {}

        unique_ids = list(set(workspace_ids))
        default_role = (
            WorkspaceRole.CREATOR.value
            if user_id is None
            else WorkspaceRole.VIEWER.value
        )
        result: dict[str, dict[str, Optional[str] | int]] = {
            ws_id: {
                "role": default_role,
                "member_count": 0,
                "campaign_count": 0,
                "owner_display_name": None,
            }
            for ws_id in unique_ids
        }

        async with async_session() as session:
            owner_rows = await session.execute(
                select(WorkspaceRow.id, UserRow.display_name)
                .outerjoin(UserRow, WorkspaceRow.owner_id == UserRow.id)
                .where(WorkspaceRow.id.in_(unique_ids))
            )
            for ws_id, owner_display_name in owner_rows.all():
                if ws_id in result:
                    result[ws_id]["owner_display_name"] = owner_display_name

            # Consolidate member_count and the per-user role into a single query
            # using conditional aggregation, reducing one DB round-trip.
            member_rows = await session.execute(
                select(
                    WorkspaceMemberRow.workspace_id,
                    func.count(WorkspaceMemberRow.user_id).label("member_count"),
                    func.max(
                        case(
                            (WorkspaceMemberRow.user_id == user_id, WorkspaceMemberRow.role),
                            else_=None,
                        )
                    ).label("user_role"),
                )
                .where(WorkspaceMemberRow.workspace_id.in_(unique_ids))
                .group_by(WorkspaceMemberRow.workspace_id)
            )
            for ws_id, member_count, user_role in member_rows.all():
                if ws_id in result:
                    result[ws_id]["member_count"] = int(member_count or 0)
                    if user_role is not None and user_id is not None:
                        result[ws_id]["role"] = user_role

            campaign_count_rows = await session.execute(
                select(
                    CampaignRow.workspace_id,
                    func.count(CampaignRow.id),
                )
                .where(CampaignRow.workspace_id.in_(unique_ids))
                .group_by(CampaignRow.workspace_id)
            )
            for ws_id, count in campaign_count_rows.all():
                if ws_id is not None and ws_id in result:
                    result[ws_id]["campaign_count"] = int(count or 0)

        return result

    async def list_workspace_campaigns(
        self,
        workspace_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        include_drafts: bool = True,
    ) -> tuple[list[Campaign], int]:
        """Return paginated campaigns that belong to *workspace_id*.

        Returns a ``(campaigns, total)`` tuple where *total* is the count of
        all matching rows (before applying LIMIT/OFFSET).
        """
        async with async_session() as session:
            base = select(CampaignRow).where(
                CampaignRow.workspace_id == workspace_id
            )
            if not include_drafts:
                base = base.where(
                    CampaignRow.status != CampaignStatus.DRAFT.value
                )

            # Total count (no deserialization)
            count_result = await session.execute(
                select(func.count()).select_from(base.subquery())
            )
            total = count_result.scalar()

            # Paginated rows
            result = await session.execute(
                base.order_by(CampaignRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.scalars().all()
            return [Campaign.model_validate_json(r.data) for r in rows], total

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
        """Return all members of *workspace_id*, including user display_name and email."""
        async with async_session() as session:
            result = await session.execute(
                select(WorkspaceMemberRow, UserRow)
                .outerjoin(UserRow, WorkspaceMemberRow.user_id == UserRow.id)
                .where(WorkspaceMemberRow.workspace_id == workspace_id)
            )
            rows = result.all()
            return [
                WorkspaceMember(
                    workspace_id=member_row.workspace_id,
                    user_id=member_row.user_id,
                    role=WorkspaceRole(member_row.role),
                    added_at=member_row.added_at,
                    display_name=user_row.display_name if user_row is not None else None,
                    email=user_row.email if user_row is not None else None,
                )
                for member_row, user_row in rows
            ]

    async def count_workspace_members(self, workspace_id: str) -> int:
        """Return the number of members in *workspace_id* using a COUNT query.

        Avoids loading the full member list when only the count is needed
        (e.g. when computing workspace summary statistics in the fallback path).
        """
        async with async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(WorkspaceMemberRow)
                .where(WorkspaceMemberRow.workspace_id == workspace_id)
            )
            return result.scalar() or 0

    async def list_workspace_campaign_calendar_data(
        self,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        """Return minimal data for the calendar view using JSON path extraction.

        Projects only ``id``, ``brief.product_or_service`` (as *campaign_name*),
        and the ``content`` JSON subtree for each campaign in *workspace_id*.
        The full campaign JSON is never deserialized, which is a significant win
        when campaigns carry large strategy / analytics payloads.

        Returns a list of dicts with keys:
          ``id``, ``campaign_name``, ``content_json`` (raw JSON string or None).
        """
        async with async_session() as session:
            result = await session.execute(
                select(
                    CampaignRow.id,
                    func.json_extract_path_text(
                        CampaignRow.data, "brief", "product_or_service"
                    ).label("campaign_name"),
                    func.json_extract_path_text(
                        CampaignRow.data, "content"
                    ).label("content_json"),
                )
                .where(CampaignRow.workspace_id == workspace_id)
            )
            return [
                {
                    "id": r.id,
                    "campaign_name": r.campaign_name,
                    "content_json": r.content_json,
                }
                for r in result.all()
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
