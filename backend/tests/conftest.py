"""
Shared test fixtures.
"""

import pytest
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.campaign import CampaignBrief, Campaign
from backend.models.user import User, UserRole
from backend.models.workspace import Workspace
from backend.tests.mock_store import InMemoryCampaignStore


# ---- Isolate tests from Foundry agent registration state ----

@pytest.fixture(autouse=True)
def _no_foundry_agents():
    """Ensure all tests use the direct-LLM path (chat_json), not the
    Foundry agent path (chat_json_with_agent), regardless of whether
    register_agents() has populated the global registry."""
    with patch("backend.agents.base_agent.get_agent_ref", return_value=None):
        yield


# ---- In-memory WorkflowSignalStore for unit tests (no DB required) ----

class InMemoryWorkflowSignalStore:
    """Dict-backed signal store for unit tests."""

    def __init__(self):
        self._signals: list[dict] = []

    async def write_signal(self, campaign_id: str, signal_type: str, payload: dict) -> str:
        signal_id = str(uuid.uuid4())
        self._signals.append({
            "id": signal_id,
            "campaign_id": campaign_id,
            "signal_type": signal_type,
            "payload": payload,
            "created_at": datetime.now(timezone.utc),
            "consumed_at": None,
        })
        return signal_id

    async def poll_signal(self, campaign_id: str, signal_type: str) -> Optional[dict]:
        for s in self._signals:
            if (
                s["campaign_id"] == campaign_id
                and s["signal_type"] == signal_type
                and s["consumed_at"] is None
            ):
                return {"id": s["id"], "payload": s["payload"]}
        return None

    async def consume_signal(self, signal_id: str) -> None:
        for s in self._signals:
            if s["id"] == signal_id:
                s["consumed_at"] = datetime.now(timezone.utc)
                return


@pytest.fixture(autouse=True)
def _in_memory_signal_store():
    """Replace the DB-backed signal store singleton with an in-memory
    implementation so tests never need a live database connection."""
    store = InMemoryWorkflowSignalStore()
    with patch(
        "backend.agents.coordinator_agent.get_workflow_signal_store",
        return_value=store,
    ), patch(
        "backend.services.campaign_workflow_service.get_workflow_signal_store",
        return_value=store,
    ):
        yield store


# ---- Role-based user fixtures ----

@pytest.fixture
def admin_user() -> User:
    """A platform admin user."""
    return User(
        id="admin-fixture-001",
        email="admin@example.com",
        display_name="Admin User",
        roles=[UserRole.ADMIN],
    )


@pytest.fixture
def builder_user() -> User:
    """A campaign builder user."""
    return User(
        id="builder-fixture-001",
        email="builder@example.com",
        display_name="Builder User",
        roles=[UserRole.CAMPAIGN_BUILDER],
    )


@pytest.fixture
def viewer_user() -> User:
    """A viewer user (read-only)."""
    return User(
        id="viewer-fixture-001",
        email="viewer@example.com",
        display_name="Viewer User",
        roles=[UserRole.VIEWER],
    )


# ---- Reusable brief & campaign fixtures ----

@pytest.fixture
def sample_brief():
    return CampaignBrief(
        product_or_service="CloudSync — cloud storage for teams",
        goal="Increase enterprise signups by 30% in Q2",
        budget=50000.0,
        currency="USD",
        start_date="2026-04-01",
        end_date="2026-06-30",
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


# ---- Workspace fixtures ----

@pytest.fixture
def sample_workspace(builder_user: User) -> Workspace:
    """A test workspace owned by the builder_user fixture."""
    now = datetime.now(timezone.utc)
    return Workspace(
        id="sample-ws-001",
        name="Sample Workspace",
        description="A test workspace for fixtures",
        owner_id=builder_user.id,
        is_personal=False,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def personal_workspace(builder_user: User) -> Workspace:
    """A personal workspace for the builder_user fixture."""
    now = datetime.now(timezone.utc)
    return Workspace(
        id="personal-ws-001",
        name="Personal",
        description=None,
        owner_id=builder_user.id,
        is_personal=True,
        created_at=now,
        updated_at=now,
    )
