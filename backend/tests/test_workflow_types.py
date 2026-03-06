"""
Unit tests for backend/agents/workflow_types.py.

Covers WorkflowAction, StageExecutionResult, and StageDefinition.
"""

import pytest
from pydantic import ValidationError

from backend.agents.workflow_types import (
    StageDefinition,
    StageExecutionResult,
    WorkflowAction,
)
from backend.models.campaign import Campaign, CampaignBrief, CampaignStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def brief():
    return CampaignBrief(product_or_service="Widget", goal="Sell more")


@pytest.fixture
def campaign(brief):
    return Campaign(brief=brief)


# ---------------------------------------------------------------------------
# WorkflowAction
# ---------------------------------------------------------------------------

class TestWorkflowAction:
    def test_values(self):
        assert WorkflowAction.CONTINUE.value == "continue"
        assert WorkflowAction.WAIT.value == "wait"
        assert WorkflowAction.COMPLETE.value == "complete"
        assert WorkflowAction.FAIL.value == "fail"

    def test_str_subclass(self):
        assert WorkflowAction.CONTINUE == "continue"
        assert isinstance(WorkflowAction.CONTINUE, str)

    def test_all_members(self):
        members = {a.value for a in WorkflowAction}
        assert members == {"continue", "wait", "complete", "fail"}

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            WorkflowAction("skip")


# ---------------------------------------------------------------------------
# StageExecutionResult
# ---------------------------------------------------------------------------

class TestStageExecutionResult:
    def test_required_fields(self, campaign):
        result = StageExecutionResult(action=WorkflowAction.CONTINUE, campaign=campaign)
        assert result.action == WorkflowAction.CONTINUE
        assert result.campaign is campaign
        assert result.next_stage is None
        assert result.reason is None

    def test_optional_fields(self, campaign):
        result = StageExecutionResult(
            action=WorkflowAction.WAIT,
            campaign=campaign,
            next_stage="review",
            reason="Awaiting human input",
        )
        assert result.next_stage == "review"
        assert result.reason == "Awaiting human input"

    def test_all_actions(self, campaign):
        for action in WorkflowAction:
            result = StageExecutionResult(action=action, campaign=campaign)
            assert result.action == action

    def test_missing_action_raises(self, campaign):
        with pytest.raises(ValidationError):
            StageExecutionResult(campaign=campaign)  # action is required

    def test_missing_campaign_raises(self):
        with pytest.raises(ValidationError):
            StageExecutionResult(action=WorkflowAction.CONTINUE)  # campaign is required

    def test_serialization(self, campaign):
        result = StageExecutionResult(
            action=WorkflowAction.COMPLETE,
            campaign=campaign,
            reason="All done",
        )
        data = result.model_dump(mode="json")
        assert data["action"] == "complete"
        assert data["reason"] == "All done"
        assert data["next_stage"] is None
        assert "brief" in data["campaign"]

    def test_roundtrip(self, campaign):
        result = StageExecutionResult(
            action=WorkflowAction.FAIL,
            campaign=campaign,
            reason="Agent error",
        )
        data = result.model_dump(mode="json")
        result2 = StageExecutionResult.model_validate(data)
        assert result2.action == WorkflowAction.FAIL
        assert result2.reason == "Agent error"
        assert result2.campaign.id == campaign.id


# ---------------------------------------------------------------------------
# StageDefinition
# ---------------------------------------------------------------------------

async def _dummy_handler(campaign: Campaign, context: dict) -> Campaign:
    return campaign


class TestStageDefinition:
    def test_construction(self):
        stage = StageDefinition(
            name="strategy",
            status=CampaignStatus.STRATEGY,
            handler=_dummy_handler,
        )
        assert stage.name == "strategy"
        assert stage.status == CampaignStatus.STRATEGY
        assert stage.handler is _dummy_handler
        assert stage.terminal_on_failure is True

    def test_condition_default_always_true(self, campaign):
        stage = StageDefinition(
            name="strategy",
            status=CampaignStatus.STRATEGY,
            handler=_dummy_handler,
        )
        assert stage.condition(campaign) is True

    def test_custom_condition(self, campaign):
        stage = StageDefinition(
            name="review",
            status=CampaignStatus.REVIEW,
            handler=_dummy_handler,
            condition=lambda c: c.status == CampaignStatus.REVIEW,
        )
        assert stage.condition(campaign) is False
        campaign.advance_status(CampaignStatus.REVIEW)
        assert stage.condition(campaign) is True

    def test_terminal_on_failure_false(self):
        stage = StageDefinition(
            name="analytics",
            status=CampaignStatus.ANALYTICS_SETUP,
            handler=_dummy_handler,
            terminal_on_failure=False,
        )
        assert stage.terminal_on_failure is False

    async def test_handler_is_awaitable(self, campaign):
        stage = StageDefinition(
            name="strategy",
            status=CampaignStatus.STRATEGY,
            handler=_dummy_handler,
        )
        result = await stage.handler(campaign, {})
        assert result is campaign
