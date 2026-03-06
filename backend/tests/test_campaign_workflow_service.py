"""
Unit tests for CampaignWorkflowService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.campaign import CampaignBrief, CampaignStatus
from backend.models.user import User, UserRole
from backend.services.campaign_workflow_service import CampaignWorkflowService, get_workflow_service
from backend.tests.mock_store import InMemoryCampaignStore


@pytest.fixture
def store():
    return InMemoryCampaignStore()


@pytest.fixture
def coordinator():
    mock = MagicMock()
    mock.run_pipeline = AsyncMock()
    return mock


@pytest.fixture
def service(store, coordinator):
    return CampaignWorkflowService(store=store, coordinator=coordinator)


@pytest.fixture
def brief():
    return CampaignBrief(
        product_or_service="TestProduct",
        goal="Increase signups",
    )


@pytest.fixture
def builder_user():
    return User(
        id="user-001",
        email="builder@example.com",
        display_name="Builder",
        roles=[UserRole.CAMPAIGN_BUILDER],
    )


# ---------------------------------------------------------------------------
# create_campaign
# ---------------------------------------------------------------------------

class TestCreateCampaign:
    async def test_create_campaign_with_user_sets_owner(self, service, brief, builder_user):
        campaign = await service.create_campaign(brief, builder_user)
        assert campaign.id is not None
        assert campaign.owner_id == builder_user.id
        assert campaign.status == CampaignStatus.DRAFT

    async def test_create_campaign_without_user_owner_is_none(self, service, brief):
        campaign = await service.create_campaign(brief, None)
        assert campaign.id is not None
        assert campaign.owner_id is None
        assert campaign.status == CampaignStatus.DRAFT

    async def test_create_campaign_persists_to_store(self, service, store, brief, builder_user):
        campaign = await service.create_campaign(brief, builder_user)
        stored = await store.get(campaign.id)
        assert stored is not None
        assert stored.id == campaign.id

    async def test_create_campaign_returns_campaign_with_brief(self, service, brief, builder_user):
        campaign = await service.create_campaign(brief, builder_user)
        assert campaign.brief.product_or_service == brief.product_or_service
        assert campaign.brief.goal == brief.goal


# ---------------------------------------------------------------------------
# start_pipeline
# ---------------------------------------------------------------------------

class TestStartPipeline:
    async def test_start_pipeline_calls_coordinator(self, service, store, brief, builder_user, coordinator):
        campaign = await store.create(brief, owner_id=builder_user.id)
        await service.start_pipeline(campaign.id)
        coordinator.run_pipeline.assert_awaited_once_with(campaign)

    async def test_start_pipeline_raises_for_unknown_campaign(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.start_pipeline("nonexistent-id")


# ---------------------------------------------------------------------------
# get_workflow_service factory
# ---------------------------------------------------------------------------

class TestGetWorkflowServiceFactory:
    def test_raises_without_coordinator_on_first_call(self):
        with patch("backend.services.campaign_workflow_service._workflow_service", None):
            with pytest.raises(RuntimeError, match="coordinator"):
                get_workflow_service(coordinator=None)

    def test_returns_same_instance_on_subsequent_calls(self, coordinator):
        mock_store = InMemoryCampaignStore()
        with patch("backend.services.campaign_workflow_service._workflow_service", None), \
             patch("backend.services.campaign_workflow_service.get_campaign_store", return_value=mock_store):
            svc1 = get_workflow_service(coordinator=coordinator)
            svc2 = get_workflow_service(coordinator=coordinator)
            assert svc1 is svc2
