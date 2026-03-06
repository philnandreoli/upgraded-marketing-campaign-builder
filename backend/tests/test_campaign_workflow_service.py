"""
Unit tests for CampaignWorkflowService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.campaign import CampaignBrief, CampaignContent, CampaignStatus, ContentApprovalStatus, ContentPiece
from backend.models.messages import ClarificationResponse, ContentApprovalResponse
from backend.models.user import User, UserRole
from backend.services.campaign_workflow_service import CampaignWorkflowService, WorkflowConflictError, get_workflow_service
from backend.tests.mock_store import InMemoryCampaignStore


@pytest.fixture
def store():
    return InMemoryCampaignStore()


@pytest.fixture
def coordinator():
    mock = MagicMock()
    mock.run_pipeline = AsyncMock()
    mock.submit_clarification = AsyncMock()
    mock.submit_content_approval = AsyncMock()
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
# submit_clarification
# ---------------------------------------------------------------------------

class TestSubmitClarification:
    async def test_raises_for_unknown_campaign(self, service):
        response = ClarificationResponse(campaign_id="nonexistent-id", answers={"q1": "a"})
        with pytest.raises(ValueError, match="not found"):
            await service.submit_clarification("nonexistent-id", response)

    async def test_raises_conflict_when_wrong_status(self, service, store, brief):
        campaign = await store.create(brief, owner_id=None)
        # Campaign starts in DRAFT status — not CLARIFICATION
        response = ClarificationResponse(campaign_id=campaign.id, answers={"q1": "a"})
        with pytest.raises(WorkflowConflictError, match="clarification"):
            await service.submit_clarification(campaign.id, response)

    async def test_calls_coordinator_when_status_is_clarification(self, service, store, brief, coordinator):
        campaign = await store.create(brief, owner_id=None)
        campaign.advance_status(CampaignStatus.CLARIFICATION)
        store._campaigns[campaign.id] = campaign

        response = ClarificationResponse(campaign_id=campaign.id, answers={"q1": "B2B"})
        await service.submit_clarification(campaign.id, response)

        coordinator.submit_clarification.assert_awaited_once_with(response)
        assert response.campaign_id == campaign.id


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


# ---------------------------------------------------------------------------
# Helpers shared across content-approval tests
# ---------------------------------------------------------------------------

def _make_piece(approval_status: ContentApprovalStatus = ContentApprovalStatus.PENDING) -> ContentPiece:
    return ContentPiece(
        content_type="headline",
        content="Buy now!",
        approval_status=approval_status,
    )


# ---------------------------------------------------------------------------
# submit_content_approval
# ---------------------------------------------------------------------------

class TestSubmitContentApproval:
    async def test_raises_for_unknown_campaign(self, service):
        response = ContentApprovalResponse(campaign_id="nonexistent", pieces=[], reject_campaign=False)
        with pytest.raises(ValueError, match="not found"):
            await service.submit_content_approval("nonexistent", response)

    async def test_calls_coordinator_and_sets_campaign_id(self, service, store, brief, coordinator):
        campaign = await store.create(brief, owner_id=None)
        response = ContentApprovalResponse(campaign_id="", pieces=[], reject_campaign=False)

        await service.submit_content_approval(campaign.id, response)

        assert response.campaign_id == campaign.id
        coordinator.submit_content_approval.assert_awaited_once_with(response)


# ---------------------------------------------------------------------------
# update_piece_decision
# ---------------------------------------------------------------------------

class TestUpdatePieceDecision:
    async def _campaign_in_approval(self, store, brief, *, status=CampaignStatus.CONTENT_APPROVAL, approval_status=ContentApprovalStatus.PENDING):
        campaign = await store.create(brief, owner_id=None)
        campaign.content = CampaignContent(pieces=[_make_piece(approval_status)])
        campaign.status = status
        store._campaigns[campaign.id] = campaign
        return campaign

    async def test_raises_for_unknown_campaign(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.update_piece_decision("nonexistent", 0, True, None, "")

    async def test_raises_conflict_when_wrong_status(self, service, store, brief):
        campaign = await self._campaign_in_approval(store, brief, status=CampaignStatus.APPROVED)
        with pytest.raises(WorkflowConflictError, match="content_approval"):
            await service.update_piece_decision(campaign.id, 0, True, None, "")

    async def test_raises_for_piece_out_of_range(self, service, store, brief):
        campaign = await self._campaign_in_approval(store, brief)
        with pytest.raises(ValueError, match="piece not found"):
            await service.update_piece_decision(campaign.id, 99, True, None, "")

    async def test_raises_immutability_guard_for_approved_piece(self, service, store, brief):
        campaign = await self._campaign_in_approval(store, brief, approval_status=ContentApprovalStatus.APPROVED)
        with pytest.raises(WorkflowConflictError, match="already-approved"):
            await service.update_piece_decision(campaign.id, 0, False, None, "")

    async def test_approve_piece_persists(self, service, store, brief):
        campaign = await self._campaign_in_approval(store, brief)
        result = await service.update_piece_decision(campaign.id, 0, True, None, "")

        assert result["approval_status"] == ContentApprovalStatus.APPROVED
        saved = await store.get(campaign.id)
        assert saved.content.pieces[0].approval_status == ContentApprovalStatus.APPROVED

    async def test_approve_piece_with_edited_content(self, service, store, brief):
        campaign = await self._campaign_in_approval(store, brief)
        await service.update_piece_decision(campaign.id, 0, True, "Edited text", "")

        saved = await store.get(campaign.id)
        assert saved.content.pieces[0].human_edited_content == "Edited text"

    async def test_reject_piece_persists_notes(self, service, store, brief):
        campaign = await self._campaign_in_approval(store, brief)
        result = await service.update_piece_decision(campaign.id, 0, False, None, "Needs work")

        assert result["approval_status"] == ContentApprovalStatus.REJECTED
        saved = await store.get(campaign.id)
        assert saved.content.pieces[0].approval_status == ContentApprovalStatus.REJECTED
        assert saved.content.pieces[0].human_notes == "Needs work"


# ---------------------------------------------------------------------------
# update_piece_notes
# ---------------------------------------------------------------------------

class TestUpdatePieceNotes:
    async def _campaign_with_approved_piece(self, store, brief):
        campaign = await store.create(brief, owner_id=None)
        campaign.content = CampaignContent(pieces=[_make_piece(ContentApprovalStatus.APPROVED)])
        store._campaigns[campaign.id] = campaign
        return campaign

    async def test_raises_for_unknown_campaign(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.update_piece_notes("nonexistent", 0, "note")

    async def test_raises_for_piece_out_of_range(self, service, store, brief):
        campaign = await self._campaign_with_approved_piece(store, brief)
        with pytest.raises(ValueError, match="piece not found"):
            await service.update_piece_notes(campaign.id, 99, "note")

    async def test_raises_conflict_when_piece_not_approved(self, service, store, brief):
        campaign = await store.create(brief, owner_id=None)
        campaign.content = CampaignContent(pieces=[_make_piece(ContentApprovalStatus.PENDING)])
        store._campaigns[campaign.id] = campaign
        with pytest.raises(WorkflowConflictError, match="approved"):
            await service.update_piece_notes(campaign.id, 0, "note")

    async def test_updates_notes_on_approved_piece(self, service, store, brief):
        campaign = await self._campaign_with_approved_piece(store, brief)
        result = await service.update_piece_notes(campaign.id, 0, "Ship it!")

        assert result["message"] == "Notes updated"
        assert result["campaign_id"] == campaign.id
        saved = await store.get(campaign.id)
        assert saved.content.pieces[0].human_notes == "Ship it!"
