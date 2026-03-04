"""
In-memory async CampaignStore for unit tests.

Mirrors the public interface of the real CampaignStore but uses a plain
dict so tests don't require a running PostgreSQL instance.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.models.campaign import Campaign, CampaignBrief
from backend.models.user import CampaignMemberRole


class InMemoryCampaignStore:
    """Async-compatible in-memory campaign store for testing."""

    def __init__(self) -> None:
        self._campaigns: dict[str, Campaign] = {}
        # (campaign_id, user_id) -> role value string
        self._members: dict[tuple[str, str], str] = {}

    async def create(self, brief: CampaignBrief, owner_id: Optional[str] = None) -> Campaign:
        campaign = Campaign(brief=brief, owner_id=owner_id)
        self._campaigns[campaign.id] = campaign
        if owner_id is not None:
            self._members[(campaign.id, owner_id)] = CampaignMemberRole.OWNER.value
        return campaign

    async def get(self, campaign_id: str) -> Optional[Campaign]:
        return self._campaigns.get(campaign_id)

    async def update(self, campaign: Campaign) -> Campaign:
        self._campaigns[campaign.id] = campaign
        return campaign

    async def list_all(self) -> list[Campaign]:
        return list(self._campaigns.values())

    async def list_by_owner(self, owner_id: str) -> list[Campaign]:
        return [c for c in self._campaigns.values() if c.owner_id == owner_id]

    async def list_accessible(self, user_id: str, is_admin: bool = False) -> list[Campaign]:
        """Return campaigns accessible to *user_id*.

        Admins see all campaigns; other users see only campaigns they are
        a member of.
        """
        if is_admin:
            return list(self._campaigns.values())
        return [
            self._campaigns[cid]
            for (cid, uid) in self._members
            if uid == user_id and cid in self._campaigns
        ]

    async def get_member_role(self, campaign_id: str, user_id: str) -> Optional[CampaignMemberRole]:
        """Return the membership role for *user_id* in *campaign_id*, or ``None`` if not a member."""
        role_str = self._members.get((campaign_id, user_id))
        if role_str is None:
            return None
        return CampaignMemberRole(role_str)

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

    async def delete(self, campaign_id: str) -> bool:
        if campaign_id in self._campaigns:
            del self._campaigns[campaign_id]
            # Remove all member entries for this campaign
            keys_to_delete = [k for k in self._members if k[0] == campaign_id]
            for k in keys_to_delete:
                del self._members[k]
            return True
        return False
