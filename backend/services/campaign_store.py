"""Compatibility shim — campaign_store has moved to backend.infrastructure.campaign_store."""
from backend.infrastructure.campaign_store import *  # noqa: F401, F403
from backend.infrastructure.campaign_store import CampaignStore, get_campaign_store  # noqa: F401
