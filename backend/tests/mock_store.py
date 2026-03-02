"""
In-memory async CampaignStore for unit tests.

Mirrors the public interface of the real CampaignStore but uses a plain
dict so tests don't require a running PostgreSQL instance.
"""

from __future__ import annotations

from typing import Optional

from backend.models.campaign import Campaign, CampaignBrief


class InMemoryCampaignStore:
    """Async-compatible in-memory campaign store for testing."""

    def __init__(self) -> None:
        self._campaigns: dict[str, Campaign] = {}

    async def create(self, brief: CampaignBrief, owner_id: Optional[str] = None) -> Campaign:
        campaign = Campaign(brief=brief, owner_id=owner_id)
        self._campaigns[campaign.id] = campaign
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

    async def delete(self, campaign_id: str) -> bool:
        if campaign_id in self._campaigns:
            del self._campaigns[campaign_id]
            return True
        return False
