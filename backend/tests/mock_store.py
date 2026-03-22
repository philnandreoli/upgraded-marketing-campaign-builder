"""
In-memory async CampaignStore for unit tests.

Mirrors the public interface of the real CampaignStore but uses a plain
dict so tests don't require a running PostgreSQL instance.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus
from backend.models.user import CampaignMember, CampaignMemberRole, User, UserRole
from backend.models.workspace import Workspace, WorkspaceMember, WorkspaceRole


class InMemoryCampaignStore:
    """Async-compatible in-memory campaign store for testing."""

    def __init__(self) -> None:
        self._campaigns: dict[str, Campaign] = {}
        # (campaign_id, user_id) -> role value string
        self._members: dict[tuple[str, str], str] = {}
        self._users: dict[str, User] = {}
        self._workspaces: dict[str, Workspace] = {}
        # (workspace_id, user_id) -> WorkspaceRole value string
        self._workspace_members: dict[tuple[str, str], str] = {}

    # ------------------------------------------------------------------
    # Campaign CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        brief: CampaignBrief,
        owner_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Campaign:
        campaign = Campaign(brief=brief, owner_id=owner_id, workspace_id=workspace_id)
        self._campaigns[campaign.id] = campaign
        if owner_id is not None:
            self._members[(campaign.id, owner_id)] = CampaignMemberRole.OWNER.value
        return campaign

    async def get(self, campaign_id: str) -> Optional[Campaign]:
        return self._campaigns.get(campaign_id)

    async def update(self, campaign: Campaign) -> Campaign:
        self._campaigns[campaign.id] = campaign
        campaign.version += 1
        return campaign

    async def list_all(self) -> list[Campaign]:
        return list(self._campaigns.values())

    async def list_by_owner(self, owner_id: str) -> list[Campaign]:
        return [c for c in self._campaigns.values() if c.owner_id == owner_id]

    async def list_by_status(self, statuses: list[CampaignStatus]) -> list[Campaign]:
        """Return all campaigns whose status is in *statuses*."""
        return [c for c in self._campaigns.values() if c.status in statuses]

    async def list_accessible(
        self,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Campaign], int]:
        """Return paginated campaigns accessible to *user_id*.

        Admin status is resolved from the ``_users`` store rather than being
        accepted as a caller-supplied flag.  Admins see all campaigns; other
        users see campaigns they are a direct member of *or* campaigns belonging
        to a workspace they are a member of.

        Returns a ``(campaigns, total)`` tuple.
        """
        user = self._users.get(user_id)
        if user is not None and user.is_admin:
            all_campaigns = list(self._campaigns.values())
            total = len(all_campaigns)
            return all_campaigns[offset:offset + limit], total

        # Workspaces the user is a member of
        user_workspaces = {
            ws_id
            for (ws_id, uid) in self._workspace_members
            if uid == user_id
        }

        result: list[Campaign] = []
        seen: set[str] = set()
        for campaign in self._campaigns.values():
            if campaign.id in seen:
                continue
            # Direct membership
            if (campaign.id, user_id) in self._members:
                result.append(campaign)
                seen.add(campaign.id)
                continue
            # Workspace membership
            if campaign.workspace_id and campaign.workspace_id in user_workspaces:
                result.append(campaign)
                seen.add(campaign.id)
        total = len(result)
        return result[offset:offset + limit], total

    async def move_campaign(
        self,
        campaign_id: str,
        workspace_id: Optional[str],
        *,
        acting_user_id: Optional[str] = None,
    ) -> Campaign:
        """Move a campaign to a different workspace (or orphan it).

        When *acting_user_id* is provided the caller must be a platform admin.
        """
        if acting_user_id is not None:
            user = self._users.get(acting_user_id)
            if user is None or not user.is_admin:
                raise PermissionError("Admin access required to move campaigns")
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id!r} not found")
        campaign.workspace_id = workspace_id
        campaign.updated_at = datetime.utcnow()
        return campaign

    # ------------------------------------------------------------------
    # Campaign membership
    # ------------------------------------------------------------------

    async def get_member_role(self, campaign_id: str, user_id: str) -> Optional[CampaignMemberRole]:
        """Return the membership role for *user_id* in *campaign_id*, or ``None`` if not a member."""
        role_str = self._members.get((campaign_id, user_id))
        if role_str is None:
            return None
        return CampaignMemberRole(role_str)

    async def get_member(self, campaign_id: str, user_id: str) -> Optional[CampaignMember]:
        """Return the full CampaignMember for *user_id* in *campaign_id*, or ``None`` if not a member."""
        role_str = self._members.get((campaign_id, user_id))
        if role_str is None:
            return None
        return CampaignMember(
            campaign_id=campaign_id,
            user_id=user_id,
            role=CampaignMemberRole(role_str),
            added_at=datetime.utcnow(),
        )

    async def add_member(
        self,
        campaign_id: str,
        user_id: str,
        role: CampaignMemberRole = CampaignMemberRole.VIEWER,
    ) -> None:
        """Add or update a campaign membership."""
        self._members[(campaign_id, user_id)] = role.value

    async def remove_member(self, campaign_id: str, user_id: str) -> bool:
        """Remove a membership; returns True if it existed."""
        key = (campaign_id, user_id)
        if key in self._members:
            del self._members[key]
            return True
        return False

    async def list_members(self, campaign_id: str) -> list[CampaignMember]:
        """Return all members of *campaign_id*."""
        return [
            CampaignMember(
                campaign_id=campaign_id,
                user_id=uid,
                role=CampaignMemberRole(role_str),
                added_at=datetime.utcnow(),
            )
            for (cid, uid), role_str in self._members.items()
            if cid == campaign_id
        ]

    # ------------------------------------------------------------------
    # User helpers
    # ------------------------------------------------------------------

    async def get_user(self, user_id: str) -> Optional[User]:
        """Return the User for *user_id*, or ``None`` if not found."""
        return self._users.get(user_id)

    def add_user(self, user: User) -> None:
        """Register a user in the in-memory store (test helper)."""
        self._users[user.id] = user

    async def delete(self, campaign_id: str, *, acting_user_id: Optional[str] = None) -> bool:
        """Delete a campaign by ID.

        When *acting_user_id* is provided the caller must be an ``owner`` member
        of the campaign.
        """
        if acting_user_id is not None:
            role_str = self._members.get((campaign_id, acting_user_id))
            if role_str != CampaignMemberRole.OWNER.value:
                raise PermissionError("User does not have delete permission")
        if campaign_id in self._campaigns:
            del self._campaigns[campaign_id]
            # Remove all member entries for this campaign
            keys_to_delete = [k for k in self._members if k[0] == campaign_id]
            for k in keys_to_delete:
                del self._members[k]
            return True
        return False

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
        """Create a workspace and add the owner as CREATOR."""
        workspace = Workspace(
            name=name,
            owner_id=owner_id,
            description=description,
            is_personal=is_personal,
        )
        self._workspaces[workspace.id] = workspace
        self._workspace_members[(workspace.id, owner_id)] = WorkspaceRole.CREATOR.value
        return workspace

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        return self._workspaces.get(workspace_id)

    async def update_workspace(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace {workspace_id!r} not found")
        if name is not None:
            workspace.name = name
        if description is not None:
            workspace.description = description
        workspace.updated_at = datetime.utcnow()
        return workspace

    async def delete_workspace(
        self,
        workspace_id: str,
        *,
        acting_user_id: Optional[str] = None,
    ) -> bool:
        """Delete a workspace.

        When *acting_user_id* is provided the caller must be a platform admin
        or a ``creator`` member of the workspace.
        """
        if acting_user_id is not None:
            user = self._users.get(acting_user_id)
            is_admin = user is not None and user.is_admin
            if not is_admin:
                role_str = self._workspace_members.get((workspace_id, acting_user_id))
                if role_str != WorkspaceRole.CREATOR.value:
                    raise PermissionError(
                        "User does not have permission to delete this workspace"
                    )
        if workspace_id not in self._workspaces:
            return False
        del self._workspaces[workspace_id]
        # Remove workspace members
        keys_to_delete = [k for k in self._workspace_members if k[0] == workspace_id]
        for k in keys_to_delete:
            del self._workspace_members[k]
        # Orphan campaigns belonging to this workspace
        for campaign in self._campaigns.values():
            if campaign.workspace_id == workspace_id:
                campaign.workspace_id = None
        return True

    async def list_workspaces(
        self, user_id: str, is_admin: bool = False
    ) -> list[Workspace]:
        if is_admin:
            return list(self._workspaces.values())
        return [
            self._workspaces[ws_id]
            for (ws_id, uid) in self._workspace_members
            if uid == user_id and ws_id in self._workspaces
        ]

    async def list_workspace_campaigns(
        self,
        workspace_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        include_drafts: bool = True,
    ) -> tuple[list[Campaign], int]:
        all_campaigns = [c for c in self._campaigns.values() if c.workspace_id == workspace_id]
        if not include_drafts:
            all_campaigns = [c for c in all_campaigns if c.status != CampaignStatus.DRAFT]
        total = len(all_campaigns)
        return all_campaigns[offset:offset + limit], total

    async def get_workspace_summaries(
        self,
        workspace_ids: list[str],
        *,
        user_id: Optional[str],
        is_admin: bool,
    ) -> dict[str, dict[str, Optional[str] | int]]:
        """Return aggregated workspace summary metadata for test parity."""
        summaries: dict[str, dict[str, Optional[str] | int]] = {}
        default_role = WorkspaceRole.CREATOR.value if user_id is None else WorkspaceRole.VIEWER.value

        for ws_id in set(workspace_ids):
            owner_display_name: Optional[str] = None
            ws = self._workspaces.get(ws_id)
            if ws is not None and ws.owner_id:
                owner = self._users.get(ws.owner_id)
                owner_display_name = owner.display_name if owner is not None else None

            role = default_role
            if user_id is not None:
                role = self._workspace_members.get((ws_id, user_id), WorkspaceRole.VIEWER.value)

            summaries[ws_id] = {
                "role": role,
                "member_count": sum(1 for (wid, _) in self._workspace_members if wid == ws_id),
                "campaign_count": sum(1 for c in self._campaigns.values() if c.workspace_id == ws_id),
                "owner_display_name": owner_display_name,
            }
        return summaries

    async def get_personal_workspace(self, user_id: str) -> Optional[Workspace]:
        for workspace in self._workspaces.values():
            if workspace.owner_id == user_id and workspace.is_personal:
                return workspace
        return None

    # ------------------------------------------------------------------
    # Workspace membership
    # ------------------------------------------------------------------

    async def get_workspace_member_role(
        self, workspace_id: str, user_id: str
    ) -> Optional[WorkspaceRole]:
        role_str = self._workspace_members.get((workspace_id, user_id))
        if role_str is None:
            return None
        return WorkspaceRole(role_str)

    async def add_workspace_member(
        self, workspace_id: str, user_id: str, role: WorkspaceRole
    ) -> None:
        self._workspace_members[(workspace_id, user_id)] = role.value

    async def remove_workspace_member(self, workspace_id: str, user_id: str) -> bool:
        key = (workspace_id, user_id)
        if key in self._workspace_members:
            del self._workspace_members[key]
            return True
        return False

    async def update_workspace_member_role(
        self, workspace_id: str, user_id: str, role: WorkspaceRole
    ) -> None:
        key = (workspace_id, user_id)
        if key not in self._workspace_members:
            raise ValueError(
                f"User {user_id!r} is not a member of workspace {workspace_id!r}"
            )
        self._workspace_members[key] = role.value

    async def list_workspace_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return [
            WorkspaceMember(
                workspace_id=workspace_id,
                user_id=uid,
                role=WorkspaceRole(role_str),
                added_at=datetime.utcnow(),
                display_name=self._users[uid].display_name if uid in self._users else None,
                email=self._users[uid].email if uid in self._users else None,
            )
            for (ws_id, uid), role_str in self._workspace_members.items()
            if ws_id == workspace_id
        ]
