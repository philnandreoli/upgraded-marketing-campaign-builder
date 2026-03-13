"""
Unit tests for optimistic locking behaviour.

Verifies that:
1. Campaign.version is set to 1 on creation.
2. InMemoryCampaignStore.update() increments the version on each write.
3. CampaignWorkflowService.update_piece_decision() retries once on a
   ConcurrentUpdateError and succeeds when the retry read returns a
   fresh campaign that can be updated cleanly.
4. CampaignWorkflowService.update_piece_notes() similarly retries.
5. A second consecutive ConcurrentUpdateError propagates to the caller.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.campaign import (
    Campaign,
    CampaignBrief,
    CampaignContent,
    CampaignStatus,
    ContentApprovalStatus,
    ContentPiece,
)
from backend.core.exceptions import ConcurrentUpdateError
from backend.application.campaign_workflow_service import CampaignWorkflowService, WorkflowConflictError
from backend.tests.mock_store import InMemoryCampaignStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_brief() -> CampaignBrief:
    return CampaignBrief(product_or_service="TestProduct", goal="Increase signups")


def _make_piece(approval_status: ContentApprovalStatus = ContentApprovalStatus.PENDING) -> ContentPiece:
    return ContentPiece(
        channel="email",
        content_type="subject_line",
        content="Hello world",
        approval_status=approval_status,
    )


# ---------------------------------------------------------------------------
# Campaign model version field
# ---------------------------------------------------------------------------

class TestCampaignVersionField:
    def test_version_defaults_to_one(self):
        campaign = Campaign(brief=_make_brief())
        assert campaign.version == 1

    def test_version_field_is_serialised(self):
        campaign = Campaign(brief=_make_brief())
        data = campaign.model_dump_json()
        assert '"version":1' in data or '"version": 1' in data

    def test_version_survives_round_trip(self):
        campaign = Campaign(brief=_make_brief())
        campaign.version = 7
        restored = Campaign.model_validate_json(campaign.model_dump_json())
        assert restored.version == 7


# ---------------------------------------------------------------------------
# InMemoryCampaignStore versioning
# ---------------------------------------------------------------------------

class TestInMemoryStoreVersioning:
    async def test_create_version_is_one(self):
        store = InMemoryCampaignStore()
        campaign = await store.create(_make_brief())
        assert campaign.version == 1

    async def test_update_increments_version(self):
        store = InMemoryCampaignStore()
        campaign = await store.create(_make_brief())
        assert campaign.version == 1

        await store.update(campaign)
        assert campaign.version == 2

        await store.update(campaign)
        assert campaign.version == 3

    async def test_get_returns_stored_version(self):
        store = InMemoryCampaignStore()
        campaign = await store.create(_make_brief())
        await store.update(campaign)  # version → 2

        fetched = await store.get(campaign.id)
        assert fetched.version == 2


# ---------------------------------------------------------------------------
# CampaignWorkflowService retry on ConcurrentUpdateError
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_signal_store():
    s = MagicMock()
    s.write_signal = AsyncMock()
    return s


class TestUpdatePieceDecisionRetry:
    """
    Tests that update_piece_decision retries once on ConcurrentUpdateError.
    """

    async def _make_service_with_failing_store(self, fail_times: int, mock_signal_store):
        """
        Returns (service, real_store).  The store's update() raises
        ConcurrentUpdateError for the first *fail_times* calls, then
        succeeds by delegating to the real InMemoryCampaignStore.
        """
        real_store = InMemoryCampaignStore()
        call_count = {"n": 0}

        original_update = real_store.update

        async def update_with_failures(campaign):
            call_count["n"] += 1
            if call_count["n"] <= fail_times:
                raise ConcurrentUpdateError("injected conflict")
            return await original_update(campaign)

        real_store.update = update_with_failures
        service = CampaignWorkflowService(store=real_store, signal_store=mock_signal_store)
        return service, real_store

    async def _setup_campaign(self, store: InMemoryCampaignStore) -> Campaign:
        brief = _make_brief()
        campaign = await store.create(brief)
        campaign.content = CampaignContent(pieces=[_make_piece()])
        campaign.status = CampaignStatus.CONTENT_APPROVAL
        store._campaigns[campaign.id] = campaign
        return campaign

    async def test_succeeds_on_first_retry(self, mock_signal_store):
        """One injected failure → retry succeeds."""
        service, store = await self._make_service_with_failing_store(1, mock_signal_store)
        campaign = await self._setup_campaign(store)

        result = await service.update_piece_decision(campaign.id, 0, True, None, "")
        assert result["approval_status"] == ContentApprovalStatus.APPROVED

    async def test_raises_on_second_failure(self, mock_signal_store):
        """Two consecutive failures exhaust the retry budget."""
        service, store = await self._make_service_with_failing_store(2, mock_signal_store)
        campaign = await self._setup_campaign(store)

        with pytest.raises(ConcurrentUpdateError):
            await service.update_piece_decision(campaign.id, 0, True, None, "")


class TestUpdatePieceNotesRetry:
    """
    Tests that update_piece_notes retries once on ConcurrentUpdateError.
    """

    async def _make_service_with_failing_store(self, fail_times: int, mock_signal_store):
        real_store = InMemoryCampaignStore()
        call_count = {"n": 0}
        original_update = real_store.update

        async def update_with_failures(campaign):
            call_count["n"] += 1
            if call_count["n"] <= fail_times:
                raise ConcurrentUpdateError("injected conflict")
            return await original_update(campaign)

        real_store.update = update_with_failures
        service = CampaignWorkflowService(store=real_store, signal_store=mock_signal_store)
        return service, real_store

    async def _setup_campaign(self, store: InMemoryCampaignStore) -> Campaign:
        brief = _make_brief()
        campaign = await store.create(brief)
        campaign.content = CampaignContent(pieces=[_make_piece(ContentApprovalStatus.APPROVED)])
        store._campaigns[campaign.id] = campaign
        return campaign

    async def test_succeeds_on_first_retry(self, mock_signal_store):
        """One injected failure → retry succeeds."""
        service, store = await self._make_service_with_failing_store(1, mock_signal_store)
        campaign = await self._setup_campaign(store)

        result = await service.update_piece_notes(campaign.id, 0, "Ship it!")
        assert result["message"] == "Notes updated"

    async def test_raises_on_second_failure(self, mock_signal_store):
        """Two consecutive failures exhaust the retry budget."""
        service, store = await self._make_service_with_failing_store(2, mock_signal_store)
        campaign = await self._setup_campaign(store)

        with pytest.raises(ConcurrentUpdateError):
            await service.update_piece_notes(campaign.id, 0, "note")
