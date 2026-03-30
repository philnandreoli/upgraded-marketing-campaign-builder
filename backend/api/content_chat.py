"""
Campaign content chat routes.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.apps.api.dependencies import get_campaign_for_read, get_campaign_for_write
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import get_campaign_store
from backend.infrastructure.content_chat_store import get_content_chat_store
from backend.infrastructure.llm_service import get_llm_service
from backend.models.campaign import Campaign, CampaignStatus
from backend.models.chat import ContentChatMessage
from backend.models.user import CampaignMemberRole, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/campaigns/{campaign_id}", tags=["content-chat"])


class ContentChatRequest(BaseModel):
    instruction: str = Field(min_length=1)
    context: Optional[str] = None
    include_score: bool = False
    stream: bool = False


class ContentChatPostResponse(BaseModel):
    message_id: str
    revised_content: str
    original_content: str


class ContentChatHistoryResponse(BaseModel):
    messages: list[ContentChatMessage]
    total: int


def _render_channel_plan_summary(campaign: Campaign) -> str:
    if campaign.channel_plan is None:
        return ""
    recs = []
    for rec in campaign.channel_plan.recommendations:
        recs.append(
            f"- {rec.channel.value}: budget={rec.budget_pct}%, timing={rec.timing}, tactics={', '.join(rec.tactics)}"
        )
    return "\n".join(recs)


def _build_system_prompt(campaign: Campaign, piece_index: int, current_content: str, extra_context: Optional[str]) -> str:
    strategy = campaign.strategy
    content = campaign.content
    brief = campaign.brief
    strategy_block = ""
    if strategy is not None:
        strategy_block = (
            f"Objectives: {strategy.objectives}\n"
            f"Target Audience: {strategy.target_audience.model_dump()}\n"
            f"Value Proposition: {strategy.value_proposition}\n"
            f"Key Messages: {strategy.key_messages}\n"
        )
    tone = content.tone_of_voice if content is not None else ""
    channel_plan = _render_channel_plan_summary(campaign)
    context_block = f"\nAdditional Context:\n{extra_context}\n" if extra_context else ""
    return (
        "You are an expert marketing copy editor assisting with campaign content revision.\n"
        "Revise only the requested content piece and return plain text only.\n\n"
        f"Campaign Brief:\n"
        f"- Product/Service: {brief.product_or_service}\n"
        f"- Goal: {brief.goal}\n"
        f"- Additional Context: {brief.additional_context}\n\n"
        f"Strategy:\n{strategy_block}\n"
        f"Content Tone of Voice:\n{tone}\n\n"
        f"Channel Plan Summary:\n{channel_plan}\n\n"
        f"Current Piece Index: {piece_index}\n"
        f"Current Piece Content:\n{current_content}\n"
        f"{context_block}"
    )


@router.post(
    "/content/{piece_index}/chat",
    response_model=ContentChatPostResponse,
)
async def chat_with_content_piece(
    campaign_id: str,
    piece_index: int,
    body: ContentChatRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
    user: Optional[User] = Depends(get_current_user),
) -> ContentChatPostResponse:
    if campaign.status != CampaignStatus.CONTENT_APPROVAL:
        raise HTTPException(status_code=409, detail="Chat is only available during content approval")

    if campaign.content is None or piece_index < 0 or piece_index >= len(campaign.content.pieces):
        raise HTTPException(status_code=422, detail="piece_index is out of range")

    if user is not None:
        if not user.is_admin:
            role = await get_campaign_store().get_member_role(campaign.id, user.id)
            if role not in (CampaignMemberRole.OWNER, CampaignMemberRole.EDITOR):
                raise HTTPException(status_code=403, detail="Insufficient permissions")

    piece = campaign.content.pieces[piece_index]
    before_content = piece.human_edited_content or piece.content

    system_prompt = _build_system_prompt(campaign, piece_index, before_content, body.context)

    chat_store = get_content_chat_store()
    recent_messages, _ = await chat_store.get_history(campaign.id, piece_index, limit=20, offset=0)
    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in recent_messages:
        llm_messages.append({"role": msg.role, "content": msg.content})
    llm_messages.append({"role": "user", "content": body.instruction})

    revised_content = await get_llm_service().chat(llm_messages)

    user_msg = await chat_store.create_message(
        campaign_id=campaign.id,
        piece_index=piece_index,
        role="user",
        content=body.instruction,
        user_id=user.id if user else None,
        metadata={"context": body.context or "", "include_score": body.include_score, "stream": body.stream},
    )

    all_messages, _ = await chat_store.get_history(campaign.id, piece_index, limit=1000, offset=0)
    non_reverted_assistant_count = sum(
        1
        for m in all_messages
        if m.role == "assistant" and not bool((m.metadata or {}).get("reverted", False))
    )
    version_number = non_reverted_assistant_count + 1

    assistant_msg = await chat_store.create_message(
        campaign_id=campaign.id,
        piece_index=piece_index,
        role="assistant",
        content=revised_content,
        user_id=None,
        metadata={
            "instruction_message_id": user_msg.id,
            "version": {
                "before": before_content,
                "after": revised_content,
                "version_number": version_number,
            },
            "include_score": body.include_score,
        },
    )

    return ContentChatPostResponse(
        message_id=assistant_msg.id,
        revised_content=revised_content,
        original_content=before_content,
    )


@router.get(
    "/content/{piece_index}/chat",
    response_model=ContentChatHistoryResponse,
)
async def get_content_chat_history(
    campaign_id: str,
    piece_index: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    campaign: Campaign = Depends(get_campaign_for_read),
) -> ContentChatHistoryResponse:
    if campaign.status != CampaignStatus.CONTENT_APPROVAL:
        raise HTTPException(status_code=409, detail="Chat is only available during content approval")
    if campaign.content is None or piece_index < 0 or piece_index >= len(campaign.content.pieces):
        raise HTTPException(status_code=422, detail="piece_index is out of range")

    messages, total = await get_content_chat_store().get_history(
        campaign_id=campaign.id,
        piece_index=piece_index,
        limit=limit,
        offset=offset,
    )
    return ContentChatHistoryResponse(messages=messages, total=total)
