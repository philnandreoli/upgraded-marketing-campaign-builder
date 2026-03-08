"""
Coordinator Agent — orchestrates the full campaign pipeline.

Responsibilities:
1. Receive a CampaignBrief and create a Campaign.
2. Dispatch tasks to each agent in sequence:
   Strategy → Content → Channel Planning → Analytics → Review/QA
3. After Review, automatically send review feedback back to Content Creator
   to regenerate improved content (Content Revision).
4. Present revised content to the human for per-piece approval (Content Approval).
5. If any pieces are rejected, re-revise only those pieces and re-present.
6. Once ALL pieces are approved, mark the campaign as approved.

The Coordinator does NOT call the LLM itself — it delegates to the
specialised agents and manages state transitions.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Optional

from backend.orchestration.base_agent import BaseAgent
from backend.orchestration.strategy_agent import StrategyAgent
from backend.orchestration.content_creator_agent import ContentCreatorAgent
from backend.orchestration.channel_planner_agent import ChannelPlannerAgent
from backend.orchestration.analytics_agent import AnalyticsAgent
from backend.orchestration.review_qa_agent import ReviewQAAgent
from backend.orchestration.workflow_types import StageDefinition, StageExecutionResult, WorkflowAction
from backend.models.campaign import (
    AnalyticsPlan,
    Campaign,
    CampaignContent,
    CampaignStatus,
    CampaignStrategy,
    ChannelPlan,
    ContentApprovalStatus,
    ContentPiece,
    ReviewFeedback,
)
from backend.models.events import (
    ClarificationRequestedEvent,
    ContentApprovalRequestedEvent,
    StageCompletedEvent,
    StageErrorEvent,
    StageStartedEvent,
)
from backend.models.messages import (
    AgentResult,
    AgentTask,
    AgentType,
    ClarificationResponse,
    ContentApprovalResponse,
)
from backend.models.workflow import WorkflowCheckpoint, WorkflowWaitType
from backend.infrastructure.campaign_store import CampaignStore, get_campaign_store
from backend.core.exceptions import WorkflowConflictError
from backend.infrastructure.workflow_checkpoint_store import (
    WorkflowCheckpointStore,
    get_workflow_checkpoint_store,
)
from backend.infrastructure.workflow_signal_store import (
    SignalType,
    WorkflowSignalStore,
    get_workflow_signal_store,
)
from backend.config import get_settings

logger = logging.getLogger(__name__)

# Type alias for the event callback the API layer can register
EventCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

# Maximum number of per-piece revision cycles before forcing completion
MAX_CONTENT_REVISION_CYCLES = 3

ALLOWED_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {CampaignStatus.CLARIFICATION, CampaignStatus.STRATEGY},
    CampaignStatus.CLARIFICATION: {CampaignStatus.STRATEGY, CampaignStatus.MANUAL_REVIEW_REQUIRED},
    CampaignStatus.STRATEGY: {CampaignStatus.CONTENT},
    CampaignStatus.CONTENT: {CampaignStatus.CHANNEL_PLANNING},
    CampaignStatus.CHANNEL_PLANNING: {CampaignStatus.ANALYTICS_SETUP},
    CampaignStatus.ANALYTICS_SETUP: {CampaignStatus.REVIEW},
    CampaignStatus.REVIEW: {CampaignStatus.CONTENT_REVISION, CampaignStatus.CONTENT_APPROVAL},
    CampaignStatus.CONTENT_REVISION: {CampaignStatus.CONTENT_APPROVAL},
    CampaignStatus.CONTENT_APPROVAL: {
        CampaignStatus.APPROVED,
        CampaignStatus.REJECTED,
        CampaignStatus.CONTENT_REVISION,
        CampaignStatus.MANUAL_REVIEW_REQUIRED,
    },
}

# Maximum seconds to wait for _content_approval_gate to persist per-piece decisions
# before the submit_content_approval API handler returns.  10 s is well above the
# expected DB-write latency (<100 ms typical) while keeping the API responsive on
# heavily loaded systems.  On timeout the handler returns anyway and the frontend
# will pick up the saved state on the next poll cycle.
_APPROVAL_SAVE_TIMEOUT_SECONDS = 10

# Seconds to wait for human input (clarification / content approval) before
# transitioning the campaign to MANUAL_REVIEW_REQUIRED.  Derived from
# PIPELINE_IDLE_TIMEOUT_DAYS (default 30 days) in AgentSettings.
_PIPELINE_IDLE_TIMEOUT_SECONDS: float = (
    get_settings().agent.pipeline_idle_timeout_days * 86_400
)


def _transform_review_output(output: dict) -> ReviewFeedback:
    """Convert the raw review-agent output dict into a ``ReviewFeedback`` model."""
    return ReviewFeedback(
        approved=output.get("approved", False),
        issues=output.get("issues", []),
        suggestions=output.get("suggestions", []),
        brand_consistency_score=output.get("brand_consistency_score", 0.0),
    )

# When True (default), _run_pipeline_stages uses the declarative StageDefinition
# loop.  Flip to False to fall back to the hand-coded sequence without a deploy.
_USE_DECLARATIVE_PIPELINE = True

# Maps declarative pipeline stage names to the campaign field key used in
# ``stage_errors``.  Used by ``retry_current_stage`` to locate the error entry.
_STAGE_TO_ERROR_KEY: dict[str, str] = {
    "strategy": "strategy",
    "content": "content",
    "channel_planning": "channel_plan",
    "analytics": "analytics_plan",
    "review": "review",
    "content_revision": "content_revision",
    "content_approval": "content_approval",
}


class CoordinatorAgent:
    """Orchestrates the marketing campaign pipeline."""

    def __init__(
        self,
        store: CampaignStore | None = None,
        on_event: EventCallback | None = None,
        checkpoint_store: WorkflowCheckpointStore | None = None,
        idle_timeout_seconds: float | None = None,
        signal_store: WorkflowSignalStore | None = None,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        self._store = store or get_campaign_store()
        self._checkpoint_store = checkpoint_store or get_workflow_checkpoint_store()
        self._signal_store = signal_store or get_workflow_signal_store()

        # Seconds to wait for human input before escalating to MANUAL_REVIEW_REQUIRED.
        # Defaults to the module-level constant (derived from PIPELINE_IDLE_TIMEOUT_DAYS).
        self._idle_timeout_seconds: float = (
            idle_timeout_seconds
            if idle_timeout_seconds is not None
            else _PIPELINE_IDLE_TIMEOUT_SECONDS
        )

        # How often (seconds) to poll the signal store while waiting for human input.
        self._poll_interval_seconds: float = poll_interval_seconds

        # Sub-agents
        self._strategy = StrategyAgent()
        self._content = ContentCreatorAgent()
        self._channel = ChannelPlannerAgent()
        self._analytics = AnalyticsAgent()
        self._review = ReviewQAAgent()

        # Declarative stage registry — ordered list of pipeline stages
        self._stages: list[StageDefinition] = [
            StageDefinition("strategy", CampaignStatus.STRATEGY, self._run_strategy_stage),
            StageDefinition("content", CampaignStatus.CONTENT, self._run_content_stage),
            StageDefinition("channel_planning", CampaignStatus.CHANNEL_PLANNING, self._run_channel_stage),
            StageDefinition("analytics", CampaignStatus.ANALYTICS_SETUP, self._run_analytics_stage),
            StageDefinition("review", CampaignStatus.REVIEW, self._run_review_stage),
            StageDefinition(
                "content_revision", CampaignStatus.CONTENT_REVISION,
                self._run_content_revision_stage,
                condition=lambda c: c.review is not None and c.content is not None,
            ),
            StageDefinition(
                "content_approval", CampaignStatus.CONTENT_APPROVAL,
                self._run_content_approval_stage,
                condition=lambda c: c.content is not None,
                terminal_on_failure=False,
            ),
        ]

        # Optional callback for pushing real-time events (WebSocket etc.)
        self._on_event = on_event

        # Holds pending clarification futures keyed by campaign_id
        self._pending_clarifications: dict[str, asyncio.Future[ClarificationResponse]] = {}

        # Holds pending content-approval futures keyed by campaign_id
        self._pending_content_approvals: dict[str, asyncio.Future[ContentApprovalResponse]] = {}

        # Resolved by _content_approval_gate after it persists per-piece decisions so
        # submit_content_approval can await the save before returning the API response.
        self._content_approval_saved: dict[str, asyncio.Future[None]] = {}

        # Per-campaign locks that guard the check-then-set sequences in
        # submit_clarification / submit_content_approval / _resolve_approval_saved
        # against concurrent calls.
        self._clarification_locks: dict[str, asyncio.Lock] = {}
        self._approval_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resume_pipeline(self, campaign_id: str) -> Campaign:
        """Resume a previously interrupted pipeline from its last checkpoint.

        Loads the campaign from the store, checks for an existing checkpoint,
        and resumes from where the pipeline was interrupted. Completed stages
        are not re-run (idempotency checks via ``_should_run_stage``).

        If no checkpoint exists the pipeline starts fresh via ``run_pipeline``.
        """
        campaign = await self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found")

        checkpoint = await self._checkpoint_store.get_checkpoint(campaign_id)
        if checkpoint is None:
            logger.info("No checkpoint for %s, starting fresh", campaign_id)
            return await self.run_pipeline(campaign)

        logger.info(
            "Resuming pipeline for campaign %s from checkpoint stage '%s'",
            campaign_id,
            checkpoint.current_stage,
        )

        await self._emit("pipeline_started", {"campaign_id": campaign.id})
        campaign_data = campaign.model_dump(mode="json")

        # Only run clarification if strategy hasn't been generated yet
        if self._should_run_stage(campaign, "strategy"):
            campaign = await self._run_clarification(campaign, campaign_data)
            campaign_data = campaign.model_dump(mode="json")

            # If clarification timed out the campaign is already in a terminal state
            if campaign.status == CampaignStatus.MANUAL_REVIEW_REQUIRED:
                logger.info(
                    "Pipeline halted after clarification timeout for campaign %s",
                    campaign.id,
                )
                await self._emit("pipeline_completed", {
                    "campaign_id": campaign.id,
                    "status": campaign.status.value,
                })
                return campaign

        # Run pipeline stages with idempotency checks to skip completed stages
        campaign = await self._run_pipeline_stages(campaign, campaign_data, skip_completed=True)

        logger.info(
            "Pipeline finished for campaign %s — status: %s",
            campaign.id,
            campaign.status.value,
        )
        await self._emit("pipeline_completed", {
            "campaign_id": campaign.id,
            "status": campaign.status.value,
        })
        return campaign

    async def retry_current_stage(self, campaign_id: str) -> Campaign:
        """Retry the current failed stage of a campaign.

        Loads the campaign and its checkpoint, identifies the current stage
        from the checkpoint, clears the stored stage error, and re-runs the
        pipeline from that stage.

        Raises ``ValueError`` if the campaign does not exist or has no
        checkpoint, and ``WorkflowConflictError`` if the checkpoint stage has
        no recorded error (i.e. nothing to retry).
        """
        campaign = await self._store.get(campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found")

        checkpoint = await self._checkpoint_store.get_checkpoint(campaign_id)
        if checkpoint is None:
            raise ValueError(f"No checkpoint found for campaign {campaign_id}; use resume instead")

        current_stage = checkpoint.current_stage
        error_key = _STAGE_TO_ERROR_KEY.get(current_stage, current_stage)

        if error_key not in campaign.stage_errors:
            raise WorkflowConflictError(
                f"Stage '{current_stage}' has no recorded error for campaign {campaign_id}"
            )

        logger.info(
            "Retrying stage '%s' for campaign %s (clearing error: %s)",
            current_stage,
            campaign_id,
            campaign.stage_errors[error_key],
        )

        # Clear the error so _should_run_stage will permit re-running this stage
        del campaign.stage_errors[error_key]
        await self._store.update(campaign)

        await self._emit("pipeline_started", {"campaign_id": campaign.id})
        campaign_data = campaign.model_dump(mode="json")

        # Run pipeline stages; skip_completed=True ensures already-finished
        # stages before the retried stage are not re-executed.
        campaign = await self._run_pipeline_stages(campaign, campaign_data, skip_completed=True)

        logger.info(
            "Retry finished for campaign %s — status: %s",
            campaign.id,
            campaign.status.value,
        )
        await self._emit("pipeline_completed", {
            "campaign_id": campaign.id,
            "status": campaign.status.value,
        })
        return campaign

    async def run_pipeline(self, campaign: Campaign) -> Campaign:
        """Run the full campaign pipeline end-to-end.

        Pipeline stages:
        1. Clarification (optional)
        2. Strategy
        3. Content
        4. Channel Planning
        5. Analytics
        6. Review / QA
        7. Content Revision (automatic — feed review back to content creator)
        8. Content Approval (human reviews each piece, may loop for rejected pieces)

        Returns the final campaign (approved or rejected).
        """
        logger.info("Pipeline started for campaign %s", campaign.id)
        await self._emit("pipeline_started", {"campaign_id": campaign.id})

        campaign_data = campaign.model_dump(mode="json")

        # 0 — Clarification gate (multi-turn strategy intake)
        campaign = await self._run_clarification(campaign, campaign_data)
        campaign_data = campaign.model_dump(mode="json")

        # If clarification timed out the campaign is already in a terminal state —
        # skip the remaining stages and return immediately.
        if campaign.status == CampaignStatus.MANUAL_REVIEW_REQUIRED:
            logger.info(
                "Pipeline halted after clarification timeout for campaign %s",
                campaign.id,
            )
            await self._emit("pipeline_completed", {
                "campaign_id": campaign.id,
                "status": campaign.status.value,
            })
            return campaign

        # Run the main pipeline stages
        campaign = await self._run_pipeline_stages(campaign, campaign_data)

        logger.info(
            "Pipeline finished for campaign %s — status: %s",
            campaign.id,
            campaign.status.value,
        )
        await self._emit("pipeline_completed", {
            "campaign_id": campaign.id,
            "status": campaign.status.value,
        })
        return campaign

    async def _run_pipeline_stages(
        self,
        campaign: Campaign,
        campaign_data: dict[str, Any],
        skip_completed: bool = False,
    ) -> Campaign:
        """Iterate over registered StageDefinition objects: condition → handler → action.

        Falls back to the hand-coded sequence when _USE_DECLARATIVE_PIPELINE is False.

        When *skip_completed* is ``True`` (resume mode) stages that already have
        output are skipped via ``_should_run_stage`` idempotency checks before
        the stage condition or handler is evaluated.
        """
        if not _USE_DECLARATIVE_PIPELINE:
            return await self._run_pipeline_stages_legacy(campaign, campaign_data)

        for stage in self._stages:
            if skip_completed and not self._should_run_stage(campaign, stage.name):
                logger.info(
                    "Skipping completed stage '%s' for campaign %s",
                    stage.name,
                    campaign.id,
                )
                continue
            if not stage.condition(campaign):
                continue
            result = await stage.handler(campaign, campaign_data)
            campaign = result.campaign
            campaign_data = campaign.model_dump(mode="json")
            if result.action in (WorkflowAction.COMPLETE, WorkflowAction.WAIT):
                return campaign
            if result.action == WorkflowAction.FAIL and stage.terminal_on_failure:
                return campaign
        return campaign

    async def _run_pipeline_stages_legacy(
        self,
        campaign: Campaign,
        campaign_data: dict[str, Any],
    ) -> Campaign:
        """Hand-coded pipeline sequence. Used when _USE_DECLARATIVE_PIPELINE is False."""
        # 1 — Strategy
        campaign = await self._run_stage(
            agent=self._strategy,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.STRATEGY,
            result_key="strategy",
            model_cls=CampaignStrategy,
        )
        campaign_data = campaign.model_dump(mode="json")
        if "strategy" in campaign.stage_errors:
            return campaign

        # 2 — Content
        campaign = await self._run_stage(
            agent=self._content,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.CONTENT,
            result_key="content",
            model_cls=CampaignContent,
        )
        campaign_data = campaign.model_dump(mode="json")
        if "content" in campaign.stage_errors:
            return campaign

        # 3 — Channel Planning
        campaign = await self._run_stage(
            agent=self._channel,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.CHANNEL_PLANNING,
            result_key="channel_plan",
            model_cls=ChannelPlan,
        )
        campaign_data = campaign.model_dump(mode="json")
        if "channel_plan" in campaign.stage_errors:
            return campaign

        # 4 — Analytics
        campaign = await self._run_stage(
            agent=self._analytics,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.ANALYTICS_SETUP,
            result_key="analytics_plan",
            model_cls=AnalyticsPlan,
        )
        campaign_data = campaign.model_dump(mode="json")
        if "analytics_plan" in campaign.stage_errors:
            return campaign

        # 5 — Review / QA
        campaign = await self._run_stage(
            agent=self._review,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.REVIEW,
            result_key="review",
            result_transformer=_transform_review_output,
        )
        campaign_data = campaign.model_dump(mode="json")
        if "review" in campaign.stage_errors:
            return campaign

        # 6 — Content Revision (automatic: feed review feedback to content creator)
        if campaign.review and campaign.content:
            campaign = await self._run_content_revision(campaign, campaign_data)
            campaign_data = campaign.model_dump(mode="json")

        # 7 — Content Approval (human reviews each piece, with re-revision loop)
        if campaign.content:
            campaign = await self._content_approval_gate(campaign, campaign_data)

        return campaign

    # ------------------------------------------------------------------
    # Stage handlers (declarative pipeline)
    # ------------------------------------------------------------------

    async def _run_strategy_stage(
        self, campaign: Campaign, campaign_data: dict[str, Any]
    ) -> StageExecutionResult:
        campaign = await self._run_stage(
            agent=self._strategy,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.STRATEGY,
            result_key="strategy",
            model_cls=CampaignStrategy,
        )
        action = WorkflowAction.FAIL if "strategy" in campaign.stage_errors else WorkflowAction.CONTINUE
        return StageExecutionResult(action=action, campaign=campaign)

    async def _run_content_stage(
        self, campaign: Campaign, campaign_data: dict[str, Any]
    ) -> StageExecutionResult:
        campaign = await self._run_stage(
            agent=self._content,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.CONTENT,
            result_key="content",
            model_cls=CampaignContent,
        )
        action = WorkflowAction.FAIL if "content" in campaign.stage_errors else WorkflowAction.CONTINUE
        return StageExecutionResult(action=action, campaign=campaign)

    async def _run_channel_stage(
        self, campaign: Campaign, campaign_data: dict[str, Any]
    ) -> StageExecutionResult:
        campaign = await self._run_stage(
            agent=self._channel,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.CHANNEL_PLANNING,
            result_key="channel_plan",
            model_cls=ChannelPlan,
        )
        action = WorkflowAction.FAIL if "channel_plan" in campaign.stage_errors else WorkflowAction.CONTINUE
        return StageExecutionResult(action=action, campaign=campaign)

    async def _run_analytics_stage(
        self, campaign: Campaign, campaign_data: dict[str, Any]
    ) -> StageExecutionResult:
        campaign = await self._run_stage(
            agent=self._analytics,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.ANALYTICS_SETUP,
            result_key="analytics_plan",
            model_cls=AnalyticsPlan,
        )
        action = WorkflowAction.FAIL if "analytics_plan" in campaign.stage_errors else WorkflowAction.CONTINUE
        return StageExecutionResult(action=action, campaign=campaign)

    async def _run_review_stage(
        self, campaign: Campaign, campaign_data: dict[str, Any]
    ) -> StageExecutionResult:
        campaign = await self._run_stage(
            agent=self._review,
            campaign=campaign,
            campaign_data=campaign_data,
            status_before=CampaignStatus.REVIEW,
            result_key="review",
            result_transformer=_transform_review_output,
        )
        action = WorkflowAction.FAIL if "review" in campaign.stage_errors else WorkflowAction.CONTINUE
        return StageExecutionResult(action=action, campaign=campaign)

    async def _run_content_revision_stage(
        self, campaign: Campaign, campaign_data: dict[str, Any]
    ) -> StageExecutionResult:
        campaign = await self._run_content_revision(campaign, campaign_data)
        # Content revision failures are non-terminal — always continue to approval
        return StageExecutionResult(action=WorkflowAction.CONTINUE, campaign=campaign)

    async def _run_content_approval_stage(
        self, campaign: Campaign, campaign_data: dict[str, Any]
    ) -> StageExecutionResult:
        campaign = await self._content_approval_gate(campaign, campaign_data)
        # Terminal stage — COMPLETE signals the loop to stop
        return StageExecutionResult(action=WorkflowAction.COMPLETE, campaign=campaign)

    async def submit_clarification(self, response: ClarificationResponse) -> None:
        """Called by the API layer when the user answers clarifying questions.

        Always writes a durable signal to the DB so cross-process coordinators
        can pick it up via poll.  If a coordinator is running in the same process
        and has an active future, the future is resolved immediately as a fast path.
        """
        # Write durable signal first so the poll loop can always find it.
        await self._signal_store.write_signal(
            response.campaign_id,
            SignalType.CLARIFICATION_RESPONSE,
            response.model_dump(mode="json"),
        )

        lock = self._clarification_locks.setdefault(response.campaign_id, asyncio.Lock())
        async with lock:
            future = self._pending_clarifications.get(response.campaign_id)
            if future is not None:
                if not future.done():
                    future.set_result(response)
                    logger.info("Clarification received for campaign %s", response.campaign_id)
                else:
                    # A concurrent call already resolved this future — do nothing.
                    logger.info(
                        "Clarification already handled for campaign %s (duplicate submission ignored)",
                        response.campaign_id,
                    )
                # Lock is no longer needed once the future is resolved; remove it
                # so the dict doesn't grow unbounded.
                self._clarification_locks.pop(response.campaign_id, None)
                return
            # No active pipeline — persist answers and restart the pipeline
            logger.info(
                "No pending clarification future for campaign %s; persisting answers and re-launching pipeline",
                response.campaign_id,
            )
            campaign = await self._store.get(response.campaign_id)
            if campaign is None:
                logger.warning(
                    "Cannot resume clarification: campaign %s not found",
                    response.campaign_id,
                )
                self._clarification_locks.pop(response.campaign_id, None)
                return
            campaign.clarification_answers = response.answers
            await self._store.update(campaign)
            asyncio.create_task(self.run_pipeline(campaign))
        # Remove after the re-launch path so any concurrent caller that queued
        # on the same lock also exits cleanly before the entry disappears.
        self._clarification_locks.pop(response.campaign_id, None)

    async def submit_content_approval(self, response: ContentApprovalResponse) -> None:
        """Called by the API layer when the human submits per-piece content approvals.

        Always writes a durable signal to the DB.  If a coordinator is running in
        the same process and has an active future, the future is resolved immediately
        as a fast path and the caller waits for the gate to persist the decisions.
        """
        # Write durable signal first so the poll loop can always find it.
        await self._signal_store.write_signal(
            response.campaign_id,
            SignalType.CONTENT_APPROVAL,
            response.model_dump(mode="json"),
        )

        lock = self._approval_locks.setdefault(response.campaign_id, asyncio.Lock())
        saved_future: asyncio.Future[None] | None = None
        no_pending = False

        async with lock:
            future = self._pending_content_approvals.get(response.campaign_id)
            if future is not None:
                if not future.done():
                    # Register a save-completion signal before resuming the gate so the gate
                    # can resolve it after _store.update().  The API handler then awaits that
                    # signal, guaranteeing the DB is updated before the frontend re-fetches.
                    loop = asyncio.get_running_loop()
                    saved_future = loop.create_future()
                    self._content_approval_saved[response.campaign_id] = saved_future

                    future.set_result(response)
                    logger.info("Content approval received for campaign %s", response.campaign_id)
                else:
                    # A concurrent call already resolved this future — do nothing.
                    logger.info(
                        "Content approval already handled for campaign %s (duplicate submission ignored)",
                        response.campaign_id,
                    )
            else:
                no_pending = True

        if saved_future is not None:
            # Wait outside the lock so we don't hold it while the pipeline processes
            # the approval — that would deadlock if _resolve_approval_saved also
            # tried to acquire the lock.
            try:
                await asyncio.wait_for(asyncio.shield(saved_future), timeout=_APPROVAL_SAVE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                logger.warning(
                    "Content approval save timed out for campaign %s",
                    response.campaign_id,
                )
            finally:
                # Remove the entries so any late call to _resolve_approval_saved (after
                # timeout) will get None from .get() and harmlessly skip set_result.
                # Also clean up the approval lock — a new one will be created for the
                # next approval cycle so the dict does not grow unbounded.
                self._content_approval_saved.pop(response.campaign_id, None)
                self._approval_locks.pop(response.campaign_id, None)
        elif no_pending:
            logger.info(
                "No pending content approval future for campaign %s — signal written to DB for poll",
                response.campaign_id,
            )

    def _resolve_approval_saved(self, campaign_id: str) -> None:
        """Signal to submit_content_approval that per-piece decisions have been persisted."""
        saved = self._content_approval_saved.get(campaign_id)
        if saved and not saved.done():
            saved.set_result(None)

    def _should_run_stage(self, campaign: Campaign, stage_name: str) -> bool:
        """Return ``True`` if *stage_name* still needs to run for *campaign*.

        Used by ``resume_pipeline`` to skip stages that have already produced
        output, providing idempotency guarantees when resuming after a server
        restart.  Stages whose output field is ``None`` (or whose state
        otherwise indicates the work is pending) return ``True``; finished
        stages return ``False``.
        """
        if stage_name == "strategy":
            return campaign.strategy is None
        if stage_name == "content":
            return campaign.content is None
        if stage_name == "channel_planning":
            return campaign.channel_plan is None
        if stage_name == "analytics":
            return campaign.analytics_plan is None
        if stage_name == "review":
            return campaign.review is None
        if stage_name == "content_revision":
            return campaign.content_revision_count == 0
        if stage_name == "content_approval":
            return campaign.status not in (
                CampaignStatus.APPROVED,
                CampaignStatus.REJECTED,
                CampaignStatus.MANUAL_REVIEW_REQUIRED,
            )
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition(self, campaign: Campaign, new_status: CampaignStatus) -> None:
        """Validate and apply a status transition.

        Self-transitions (same → same) are silently allowed to support pipeline
        resume and looping gates (e.g. re-entering CONTENT_APPROVAL after a
        revision cycle).  Cross-state transitions that are not listed in
        ALLOWED_TRANSITIONS raise ``ValueError``.
        """
        if campaign.status != new_status:
            allowed = ALLOWED_TRANSITIONS.get(campaign.status, set())
            if new_status not in allowed:
                raise ValueError(
                    f"Invalid transition {campaign.status.value} -> {new_status.value} "
                    f"for campaign {campaign.id}"
                )
        campaign.advance_status(new_status)

    async def _run_stage(
        self,
        agent: BaseAgent,
        campaign: Campaign,
        campaign_data: dict[str, Any],
        status_before: CampaignStatus,
        result_key: str,
        model_cls: type | None = None,
        extra_instruction: str = "",
        result_transformer: Callable[[dict], Any] | None = None,
    ) -> Campaign:
        """Run a single agent stage and persist the result on the campaign.

        ``result_transformer``, when provided, is called with the raw output dict
        and its return value is stored on the campaign.  This is used for stages
        (e.g. review) whose output requires custom construction rather than a
        plain ``model_cls.model_validate`` call.
        """
        self._transition(campaign, status_before)
        await self._save_checkpoint(campaign, status_before.value)
        await self._persist_and_emit(campaign, "stage_started", StageStartedEvent(
            campaign_id=campaign.id,
            stage=status_before.value,
        ).model_dump(mode="json"))

        task = AgentTask(
            task_id=str(uuid.uuid4()),
            agent_type=agent.agent_type,
            campaign_id=campaign.id,
            instruction=extra_instruction,
        )

        result: AgentResult = await agent.run(task, campaign_data)

        if not result.success:
            logger.error(
                "Stage %s failed for campaign %s: %s",
                status_before.value,
                campaign.id,
                result.error,
            )
            campaign.stage_errors[result_key] = result.error or "Unknown error"
            await self._persist_and_emit(campaign, "stage_error", StageErrorEvent(
                campaign_id=campaign.id,
                stage=status_before.value,
                error=result.error or "Unknown error",
            ).model_dump(mode="json"))
            return campaign

        # Hydrate the model and attach to the campaign
        if result_transformer is not None:
            model_instance = result_transformer(result.output)
        else:
            assert model_cls is not None, (
                "_run_stage: model_cls must be provided when result_transformer is not set"
            )
            model_instance = model_cls.model_validate(result.output)
        setattr(campaign, result_key, model_instance)
        await self._persist_and_emit(campaign, "stage_completed", StageCompletedEvent(
            campaign_id=campaign.id,
            stage=status_before.value,
            output=result.output,
        ).model_dump(mode="json"))
        return campaign

    # ------------------------------------------------------------------
    # Content Revision (automatic — review feedback -> content creator)
    # ------------------------------------------------------------------

    async def _run_content_revision(
        self,
        campaign: Campaign,
        campaign_data: dict[str, Any],
    ) -> Campaign:
        """Automatically send review feedback back to the content creator
        to regenerate improved content."""
        self._transition(campaign, CampaignStatus.CONTENT_REVISION)
        await self._save_checkpoint(campaign, "content_revision")
        await self._persist_and_emit(campaign, "stage_started", StageStartedEvent(
            campaign_id=campaign.id,
            stage="content_revision",
        ).model_dump(mode="json"))

        # Save original content for comparison
        if campaign.original_content is None and campaign.content:
            campaign.original_content = campaign.content.model_copy(deep=True)

        task = AgentTask(
            task_id=str(uuid.uuid4()),
            agent_type=AgentType.CONTENT_CREATOR,
            campaign_id=campaign.id,
            instruction="",
        )

        try:
            result = await self._content.revise(task, campaign_data)
            if not result.success:
                raise RuntimeError(result.error or "Content revision failed")
            result_data = result.output

            # Set all pieces to pending approval
            for piece in result_data.get("pieces", []):
                piece["approval_status"] = ContentApprovalStatus.PENDING
                piece["human_edited_content"] = None
                piece["human_notes"] = ""

            revised_content = CampaignContent.model_validate(result_data)
            campaign.content = revised_content
            campaign.content_revision_count += 1
            await self._persist_and_emit(campaign, "stage_completed", StageCompletedEvent(
                campaign_id=campaign.id,
                stage="content_revision",
                output=result_data,
            ).model_dump(mode="json"))
        except Exception as exc:
            logger.exception("Content revision failed for campaign %s: %s", campaign.id, exc)
            campaign.stage_errors["content_revision"] = str(exc)
            await self._persist_and_emit(campaign, "stage_error", StageErrorEvent(
                campaign_id=campaign.id,
                stage="content_revision",
                error=str(exc),
            ).model_dump(mode="json"))

        return campaign

    # ------------------------------------------------------------------
    # Content Approval (human-in-the-loop, per-piece)
    # ------------------------------------------------------------------

    async def _content_approval_gate(
        self,
        campaign: Campaign,
        campaign_data: dict[str, Any],
    ) -> Campaign:
        """Pause pipeline for human to approve each content piece individually.

        Loops: if pieces are rejected, re-revise only those pieces and
        re-present for approval until all approved or campaign rejected.
        """
        for cycle in range(MAX_CONTENT_REVISION_CYCLES + 1):
            self._transition(campaign, CampaignStatus.CONTENT_APPROVAL)
            # Emit content for human review
            content_data = campaign.content.model_dump(mode="json") if campaign.content else {}
            await self._persist_and_emit(campaign, "content_approval_requested", ContentApprovalRequestedEvent(
                campaign_id=campaign.id,
                content=content_data,
                revision_cycle=cycle,
            ).model_dump(mode="json"))

            # Wait for human response.  Polls the DB signal store every
            # _poll_interval_seconds; resolves immediately via in-process future
            # when running in a single-process deployment (fast path).
            loop = asyncio.get_running_loop()
            future: asyncio.Future[ContentApprovalResponse] = loop.create_future()
            self._pending_content_approvals[campaign.id] = future
            wait_started_at = datetime.utcnow()
            expires_at = wait_started_at + timedelta(seconds=self._idle_timeout_seconds)
            await self._save_checkpoint(
                campaign, "content_approval",
                wait_type=WorkflowWaitType.CONTENT_APPROVAL,
                wait_started_at=wait_started_at,
                expires_at=expires_at,
            )

            human_response: ContentApprovalResponse | None = None
            timed_out = False
            deadline = loop.time() + self._idle_timeout_seconds
            try:
                while True:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        timed_out = True
                        break

                    # Fast path: in-process future already resolved.
                    if future.done() and not future.cancelled():
                        human_response = future.result()
                        break

                    # Durable path: check DB signal store.
                    signal = await self._signal_store.poll_signal(
                        campaign.id, SignalType.CONTENT_APPROVAL
                    )
                    if signal is not None:
                        await self._signal_store.consume_signal(signal["id"])
                        human_response = ContentApprovalResponse(**signal["payload"])
                        if not future.done():
                            future.set_result(human_response)
                        break

                    # Neither ready — wait up to poll_interval or until future resolves.
                    poll_wait = min(self._poll_interval_seconds, remaining)
                    try:
                        human_response = await asyncio.wait_for(
                            asyncio.shield(future), timeout=poll_wait
                        )
                        break
                    except asyncio.TimeoutError:
                        pass  # Continue polling
            finally:
                self._pending_content_approvals.pop(campaign.id, None)

            if timed_out or human_response is None:
                logger.warning(
                    "Content approval wait timed out for campaign %s — escalating to MANUAL_REVIEW_REQUIRED",
                    campaign.id,
                )
                self._transition(campaign, CampaignStatus.MANUAL_REVIEW_REQUIRED)
                await self._store.update(campaign)
                await self._emit("wait_timeout", {
                    "campaign_id": campaign.id,
                    "wait_type": WorkflowWaitType.CONTENT_APPROVAL,
                    "stage": "content_approval",
                })
                return campaign

            await self._save_checkpoint(campaign, "content_approval")

            # Handle campaign-level rejection
            if human_response.reject_campaign:
                self._transition(campaign, CampaignStatus.REJECTED)
                await self._store.update(campaign)
                # Signal the API handler that decisions have been persisted
                self._resolve_approval_saved(campaign.id)
                await self._emit("content_approval_completed", {
                    "campaign_id": campaign.id,
                    "approved": False,
                    "rejected_campaign": True,
                })
                return campaign

            # Apply per-piece approvals
            if campaign.content:
                for piece_approval in human_response.pieces:
                    idx = piece_approval.piece_index
                    if 0 <= idx < len(campaign.content.pieces):
                        piece = campaign.content.pieces[idx]
                        # Once a piece is approved its content is immutable — skip any
                        # attempt to modify content or human_edited_content.
                        if piece.approval_status == ContentApprovalStatus.APPROVED:
                            continue
                        if piece_approval.approved:
                            piece.approval_status = ContentApprovalStatus.APPROVED
                            if piece_approval.edited_content is not None:
                                piece.human_edited_content = piece_approval.edited_content
                            if piece_approval.notes:
                                piece.human_notes = piece_approval.notes
                        else:
                            piece.approval_status = ContentApprovalStatus.REJECTED
                            piece.human_notes = piece_approval.notes or ""
                            if piece_approval.edited_content is not None:
                                piece.human_edited_content = piece_approval.edited_content

                await self._store.update(campaign)

            # Signal the API handler that per-piece decisions have been persisted
            self._resolve_approval_saved(campaign.id)

            # Check if all pieces are approved
            all_approved = all(
                p.approval_status == ContentApprovalStatus.APPROVED
                for p in (campaign.content.pieces if campaign.content else [])
            )

            if all_approved:
                self._transition(campaign, CampaignStatus.APPROVED)
                await self._persist_and_emit(campaign, "content_approval_completed", {
                    "campaign_id": campaign.id,
                    "approved": True,
                })
                return campaign

            # Some pieces rejected — re-revise only rejected pieces
            rejected_pieces = [
                p.model_dump(mode="json")
                for p in (campaign.content.pieces if campaign.content else [])
                if p.approval_status == ContentApprovalStatus.REJECTED
            ]

            if rejected_pieces and cycle < MAX_CONTENT_REVISION_CYCLES:
                await self._emit("content_re_revision_started", {
                    "campaign_id": campaign.id,
                    "rejected_count": len(rejected_pieces),
                    "cycle": cycle + 1,
                })

                campaign = await self._revise_rejected_pieces(
                    campaign, campaign_data, rejected_pieces,
                )
                campaign_data = campaign.model_dump(mode="json")
                # Loop back to present for approval again
            else:
                # Max cycles reached — escalate for manual review
                self._transition(campaign, CampaignStatus.MANUAL_REVIEW_REQUIRED)
                await self._persist_and_emit(campaign, "content_approval_completed", {
                    "campaign_id": campaign.id,
                    "approved": False,
                    "needs_manual_review": True,
                    "note": "Max revision cycles reached — escalated for manual review",
                })
                return campaign

        return campaign

    async def _revise_rejected_pieces(
        self,
        campaign: Campaign,
        campaign_data: dict[str, Any],
        rejected_pieces: list[dict[str, Any]],
    ) -> Campaign:
        """Re-revise only the rejected content pieces via the Content Creator."""
        task = AgentTask(
            task_id=str(uuid.uuid4()),
            agent_type=AgentType.CONTENT_CREATOR,
            campaign_id=campaign.id,
            instruction="",
        )

        try:
            result = await self._content.revise_pieces(task, campaign_data, rejected_pieces)
            if not result.success:
                raise RuntimeError(result.error or "Piece revision failed")
            result_data = result.output
            revised_pieces = result_data.get("pieces", [])

            # Match revised pieces back to rejected ones and update in-place
            if campaign.content:
                for revised in revised_pieces:
                    for i, existing in enumerate(campaign.content.pieces):
                        if (
                            existing.approval_status == ContentApprovalStatus.REJECTED
                            and existing.content_type == revised.get("content_type", "")
                            and existing.channel == revised.get("channel", "")
                            and existing.variant == revised.get("variant", "A")
                        ):
                            existing.content = revised.get("content", existing.content)
                            existing.notes = revised.get("notes", "")
                            existing.approval_status = ContentApprovalStatus.PENDING
                            existing.human_edited_content = None
                            existing.human_notes = ""
                            break

                # Reset any remaining rejected pieces to pending for re-review
                for piece in campaign.content.pieces:
                    if piece.approval_status == ContentApprovalStatus.REJECTED:
                        piece.approval_status = ContentApprovalStatus.PENDING

                campaign.content_revision_count += 1
                await self._store.update(campaign)

        except Exception as exc:
            logger.exception("Piece re-revision failed for campaign %s: %s", campaign.id, exc)
            # On failure, reset rejected pieces to pending so human can still approve
            if campaign.content:
                for piece in campaign.content.pieces:
                    if piece.approval_status == ContentApprovalStatus.REJECTED:
                        piece.approval_status = ContentApprovalStatus.PENDING
                await self._store.update(campaign)

        return campaign

    async def _save_checkpoint(
        self,
        campaign: Campaign,
        stage: str,
        wait_type: WorkflowWaitType | None = None,
        wait_started_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        """Persist a workflow checkpoint for the given stage.

        Fail-safe: if the write fails the pipeline continues unchanged.
        """
        try:
            now = datetime.utcnow()
            checkpoint = WorkflowCheckpoint(
                campaign_id=campaign.id,
                current_stage=stage,
                wait_type=wait_type,
                revision_cycle=campaign.content_revision_count,
                wait_started_at=wait_started_at,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            await self._checkpoint_store.save_checkpoint(checkpoint)
        except Exception:
            logger.warning(
                "Failed to save checkpoint for campaign %s, continuing",
                campaign.id,
                exc_info=True,
            )

    async def _persist_and_emit(
        self,
        campaign: Campaign,
        event_name: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Persist the campaign and optionally emit an event."""
        await self._store.update(campaign)
        if event_name:
            await self._emit(event_name, payload or {"campaign_id": campaign.id})

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        """Fire an event callback if one is registered."""
        if self._on_event:
            try:
                await self._on_event(event, data)
            except Exception:
                logger.exception("Event callback failed for %s", event)

    # ------------------------------------------------------------------
    # Clarification gate
    # ------------------------------------------------------------------

    async def _run_clarification(
        self,
        campaign: Campaign,
        campaign_data: dict[str, Any],
    ) -> Campaign:
        """Ask the Strategy Agent whether it needs follow-up info.

        If it does, pause the pipeline and wait for the user to answer.
        """
        await self._emit("clarification_started", {"campaign_id": campaign.id})

        clarification = await self._strategy.gather_clarifications(campaign_data)

        if not clarification.get("needs_clarification", False):
            await self._emit("clarification_skipped", {"campaign_id": campaign.id})
            return campaign

        # Store questions on the campaign so the frontend can display them
        questions = clarification.get("questions", [])
        campaign.clarification_questions = questions
        self._transition(campaign, CampaignStatus.CLARIFICATION)
        await self._store.update(campaign)

        # If answers were already submitted (e.g. user returned after navigating
        # away, or the pipeline was re-launched after a server restart), skip
        # the future-based wait and continue immediately.
        if campaign.clarification_answers:
            logger.info(
                "Clarification answers already present for campaign %s — skipping wait",
                campaign.id,
            )
            await self._emit("clarification_completed", {
                "campaign_id": campaign.id,
                "answers": campaign.clarification_answers,
            })
            return campaign

        # Populate typed question objects for the event payload
        await self._emit("clarification_requested", ClarificationRequestedEvent(
            campaign_id=campaign.id,
            questions=questions,
            context_summary=clarification.get("context_summary", ""),
        ).model_dump(mode="json"))

        # Wait for user answers.  Polls the DB signal store every
        # _poll_interval_seconds; resolves immediately via in-process future
        # when running in a single-process deployment (fast path).
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ClarificationResponse] = loop.create_future()
        self._pending_clarifications[campaign.id] = future
        wait_started_at = datetime.utcnow()
        expires_at = wait_started_at + timedelta(seconds=self._idle_timeout_seconds)
        await self._save_checkpoint(
            campaign, "clarification",
            wait_type=WorkflowWaitType.CLARIFICATION,
            wait_started_at=wait_started_at,
            expires_at=expires_at,
        )

        user_response: ClarificationResponse | None = None
        timed_out = False
        deadline = loop.time() + self._idle_timeout_seconds
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    timed_out = True
                    break

                # Fast path: in-process future already resolved.
                if future.done() and not future.cancelled():
                    user_response = future.result()
                    break

                # Durable path: check DB signal store.
                signal = await self._signal_store.poll_signal(
                    campaign.id, SignalType.CLARIFICATION_RESPONSE
                )
                if signal is not None:
                    await self._signal_store.consume_signal(signal["id"])
                    user_response = ClarificationResponse(**signal["payload"])
                    if not future.done():
                        future.set_result(user_response)
                    break

                # Neither ready — wait up to poll_interval or until future resolves.
                poll_wait = min(self._poll_interval_seconds, remaining)
                try:
                    user_response = await asyncio.wait_for(
                        asyncio.shield(future), timeout=poll_wait
                    )
                    break
                except asyncio.TimeoutError:
                    pass  # Continue polling
        finally:
            self._pending_clarifications.pop(campaign.id, None)

        if timed_out or user_response is None:
            logger.warning(
                "Clarification wait timed out for campaign %s — escalating to MANUAL_REVIEW_REQUIRED",
                campaign.id,
            )
            self._transition(campaign, CampaignStatus.MANUAL_REVIEW_REQUIRED)
            await self._store.update(campaign)
            await self._emit("wait_timeout", {
                "campaign_id": campaign.id,
                "wait_type": WorkflowWaitType.CLARIFICATION,
                "stage": "clarification",
            })
            return campaign

        await self._save_checkpoint(campaign, "clarification")

        # Persist answers on the campaign
        campaign.clarification_answers = user_response.answers
        await self._persist_and_emit(campaign, "clarification_completed", {
            "campaign_id": campaign.id,
            "answers": user_response.answers,
        })

        return campaign
