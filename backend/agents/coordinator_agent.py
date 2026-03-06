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
from typing import Any, Callable, Coroutine, Optional

from backend.agents.base_agent import BaseAgent
from backend.agents.strategy_agent import StrategyAgent
from backend.agents.content_creator_agent import ContentCreatorAgent
from backend.agents.channel_planner_agent import ChannelPlannerAgent
from backend.agents.analytics_agent import AnalyticsAgent
from backend.agents.review_qa_agent import ReviewQAAgent
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
from backend.models.messages import (
    AgentResult,
    AgentTask,
    AgentType,
    ClarificationResponse,
    ContentApprovalResponse,
)
from backend.services.campaign_store import CampaignStore, get_campaign_store

logger = logging.getLogger(__name__)

# Type alias for the event callback the API layer can register
EventCallback = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

# Maximum number of per-piece revision cycles before forcing completion
MAX_CONTENT_REVISION_CYCLES = 3

ALLOWED_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {CampaignStatus.CLARIFICATION, CampaignStatus.STRATEGY},
    CampaignStatus.CLARIFICATION: {CampaignStatus.STRATEGY},
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
    },
}

# Maximum seconds to wait for _content_approval_gate to persist per-piece decisions
# before the submit_content_approval API handler returns.  10 s is well above the
# expected DB-write latency (<100 ms typical) while keeping the API responsive on
# heavily loaded systems.  On timeout the handler returns anyway and the frontend
# will pick up the saved state on the next poll cycle.
_APPROVAL_SAVE_TIMEOUT_SECONDS = 10


class CoordinatorAgent:
    """Orchestrates the marketing campaign pipeline."""

    def __init__(
        self,
        store: CampaignStore | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self._store = store or get_campaign_store()

        # Sub-agents
        self._strategy = StrategyAgent()
        self._content = ContentCreatorAgent()
        self._channel = ChannelPlannerAgent()
        self._analytics = AnalyticsAgent()
        self._review = ReviewQAAgent()

        # Optional callback for pushing real-time events (WebSocket etc.)
        self._on_event = on_event

        # Holds pending clarification futures keyed by campaign_id
        self._pending_clarifications: dict[str, asyncio.Future[ClarificationResponse]] = {}

        # Holds pending content-approval futures keyed by campaign_id
        self._pending_content_approvals: dict[str, asyncio.Future[ContentApprovalResponse]] = {}

        # Resolved by _content_approval_gate after it persists per-piece decisions so
        # submit_content_approval can await the save before returning the API response.
        self._content_approval_saved: dict[str, asyncio.Future[None]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
    ) -> Campaign:
        """Run Strategy -> Content -> Channel -> Analytics -> Review -> Content Revision -> Content Approval."""
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
        campaign = await self._run_review(campaign, campaign_data)
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

    async def submit_clarification(self, response: ClarificationResponse) -> None:
        """Called by the API layer when the user answers clarifying questions."""
        future = self._pending_clarifications.get(response.campaign_id)
        if future and not future.done():
            future.set_result(response)
            logger.info("Clarification received for campaign %s", response.campaign_id)
        else:
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
                return
            campaign.clarification_answers = response.answers
            await self._store.update(campaign)
            asyncio.create_task(self.run_pipeline(campaign))

    async def submit_content_approval(self, response: ContentApprovalResponse) -> None:
        """Called by the API layer when the human submits per-piece content approvals."""
        future = self._pending_content_approvals.get(response.campaign_id)
        if future and not future.done():
            # Register a save-completion signal before resuming the gate so the gate
            # can resolve it after _store.update().  The API handler then awaits that
            # signal, guaranteeing the DB is updated before the frontend re-fetches.
            loop = asyncio.get_running_loop()
            saved_future: asyncio.Future[None] = loop.create_future()
            self._content_approval_saved[response.campaign_id] = saved_future

            future.set_result(response)
            logger.info("Content approval received for campaign %s", response.campaign_id)

            # Wait for the gate to persist decisions (with a generous timeout so a
            # slow DB write doesn't block forever, but the frontend still re-fetches
            # fresh data in the common case).
            try:
                await asyncio.wait_for(asyncio.shield(saved_future), timeout=_APPROVAL_SAVE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                logger.warning(
                    "Content approval save timed out for campaign %s",
                    response.campaign_id,
                )
            finally:
                # Remove the entry so any late call to _resolve_approval_saved (after
                # timeout) will get None from .get() and harmlessly skip set_result.
                self._content_approval_saved.pop(response.campaign_id, None)
        else:
            logger.warning(
                "No pending content approval for campaign %s",
                response.campaign_id,
            )

    def _resolve_approval_saved(self, campaign_id: str) -> None:
        """Signal to submit_content_approval that per-piece decisions have been persisted."""
        saved = self._content_approval_saved.get(campaign_id)
        if saved and not saved.done():
            saved.set_result(None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition(self, campaign: Campaign, new_status: CampaignStatus) -> None:
        """Validate and apply a status transition.

        Logs a warning if the transition is not in ALLOWED_TRANSITIONS but
        still applies it — warn-only for now (will become a hard error in 5.3).
        """
        allowed = ALLOWED_TRANSITIONS.get(campaign.status, set())
        if new_status not in allowed:
            logger.warning(
                "Unexpected transition %s -> %s for campaign %s",
                campaign.status.value, new_status.value, campaign.id,
            )
        campaign.advance_status(new_status)

    async def _run_stage(
        self,
        agent: BaseAgent,
        campaign: Campaign,
        campaign_data: dict[str, Any],
        status_before: CampaignStatus,
        result_key: str,
        model_cls: type,
        extra_instruction: str = "",
    ) -> Campaign:
        """Run a single agent stage and persist the result on the campaign."""
        self._transition(campaign, status_before)
        await self._persist_and_emit(campaign, "stage_started", {
            "campaign_id": campaign.id,
            "stage": status_before.value,
        })

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
            await self._persist_and_emit(campaign, "stage_error", {
                "campaign_id": campaign.id,
                "stage": status_before.value,
                "error": result.error,
            })
            return campaign

        # Hydrate the Pydantic model and attach to the campaign
        model_instance = model_cls.model_validate(result.output)
        setattr(campaign, result_key, model_instance)
        await self._persist_and_emit(campaign, "stage_completed", {
            "campaign_id": campaign.id,
            "stage": status_before.value,
            "output": result.output,
        })
        return campaign

    async def _run_review(
        self,
        campaign: Campaign,
        campaign_data: dict[str, Any],
    ) -> Campaign:
        """Run the Review/QA agent."""
        self._transition(campaign, CampaignStatus.REVIEW)
        await self._persist_and_emit(campaign, "stage_started", {
            "campaign_id": campaign.id,
            "stage": "review",
        })

        task = AgentTask(
            task_id=str(uuid.uuid4()),
            agent_type=AgentType.REVIEW_QA,
            campaign_id=campaign.id,
            instruction="",
        )

        result = await self._review.run(task, campaign_data)

        if not result.success:
            campaign.stage_errors["review"] = result.error or "Unknown error"
            await self._persist_and_emit(campaign, "stage_error", {
                "campaign_id": campaign.id,
                "stage": "review",
                "error": result.error,
            })
            return campaign

        # Persist AI review
        review_output = result.output
        review_feedback = ReviewFeedback(
            approved=review_output.get("approved", False),
            issues=review_output.get("issues", []),
            suggestions=review_output.get("suggestions", []),
            brand_consistency_score=review_output.get("brand_consistency_score", 0.0),
        )
        campaign.review = review_feedback
        await self._persist_and_emit(campaign, "stage_completed", {
            "campaign_id": campaign.id,
            "stage": "review",
            "output": review_output,
        })

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
        await self._persist_and_emit(campaign, "stage_started", {
            "campaign_id": campaign.id,
            "stage": "content_revision",
        })

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
            await self._persist_and_emit(campaign, "stage_completed", {
                "campaign_id": campaign.id,
                "stage": "content_revision",
                "output": result_data,
            })
        except Exception as exc:
            logger.exception("Content revision failed for campaign %s: %s", campaign.id, exc)
            campaign.stage_errors["content_revision"] = str(exc)
            await self._persist_and_emit(campaign, "stage_error", {
                "campaign_id": campaign.id,
                "stage": "content_revision",
                "error": str(exc),
            })

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
            await self._persist_and_emit(campaign, "content_approval_requested", {
                "campaign_id": campaign.id,
                "content": content_data,
                "revision_cycle": cycle,
            })

            # Wait for human response
            loop = asyncio.get_running_loop()
            future: asyncio.Future[ContentApprovalResponse] = loop.create_future()
            self._pending_content_approvals[campaign.id] = future

            try:
                human_response = await future
            finally:
                self._pending_content_approvals.pop(campaign.id, None)

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
                # Max cycles reached — approve remaining as-is
                self._transition(campaign, CampaignStatus.APPROVED)
                await self._persist_and_emit(campaign, "content_approval_completed", {
                    "campaign_id": campaign.id,
                    "approved": True,
                    "note": "Max revision cycles reached",
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
        await self._emit("clarification_requested", {
            "campaign_id": campaign.id,
            "questions": questions,
            "context_summary": clarification.get("context_summary", ""),
        })

        # Wait for user answers (same future pattern as content approval)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ClarificationResponse] = loop.create_future()
        self._pending_clarifications[campaign.id] = future

        try:
            user_response = await future
        finally:
            self._pending_clarifications.pop(campaign.id, None)

        # Persist answers on the campaign
        campaign.clarification_answers = user_response.answers
        await self._persist_and_emit(campaign, "clarification_completed", {
            "campaign_id": campaign.id,
            "answers": user_response.answers,
        })

        return campaign
