"""
Shared test fixtures.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.campaign import CampaignBrief, Campaign
from backend.tests.mock_store import InMemoryCampaignStore


# ---- Isolate tests from Foundry agent registration state ----

@pytest.fixture(autouse=True)
def _no_foundry_agents():
    """Ensure all tests use the direct-LLM path (chat_json), not the
    Foundry agent path (chat_json_with_agent), regardless of whether
    register_agents() has populated the global registry."""
    with patch("backend.agents.base_agent.get_agent_ref", return_value=None):
        yield


# ---- Reusable brief & campaign fixtures ----

@pytest.fixture
def sample_brief():
    return CampaignBrief(
        product_or_service="CloudSync — cloud storage for teams",
        goal="Increase enterprise signups by 30% in Q2",
        budget=50000.0,
        currency="USD",
        timeline="3 months",
        additional_context="Focus on mid-market companies (50-500 employees)",
    )


@pytest.fixture
def sample_campaign(sample_brief):
    return Campaign(brief=sample_brief)


@pytest.fixture
def campaign_store():
    """Fresh async in-memory store for each test (no database required)."""
    return InMemoryCampaignStore()


@pytest.fixture
def mock_llm_service():
    """A mocked LLMService that returns configurable JSON responses."""
    service = MagicMock()
    service.chat = AsyncMock(return_value="{}")
    service.chat_json = AsyncMock(return_value="{}")
    return service
