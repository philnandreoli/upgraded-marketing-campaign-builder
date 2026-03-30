"""Campaign content chat routes."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from backend.api.websocket import manager
from backend.apps.api.dependencies import (
    get_campaign_for_chat_read,
    get_campaign_for_chat_write,
)
from backend.core.exceptions import ConcurrentUpdateError
from backend.core.rate_limit import limiter
from backend.infrastructure.auth import get_current_user
from backend.infrastructure.campaign_store import CampaignStore, get_campaign_store
from backend.infrastructure.content_chat_store import ContentChatStore, get_content_chat_store
from backend.infrastructure.llm_service import LLMService, get_llm_service
from backend.models.campaign import Campaign
from backend.models.chat import ContentChatMessage
from backend.models.user import User

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


class ContentChatStreamAcceptedResponse(BaseModel):
    message_id: str
    status: str


class ContentChatHistoryResponse(BaseModel):
    messages: list[ContentChatMessage]
    total: int


class ContentVersionItem(BaseModel):
    version_number: int
    content: str
    created_at: datetime
    message_id: Optional[str] = None


class ContentVersionsResponse(BaseModel):
    versions: list[ContentVersionItem]


class RevertResponse(BaseModel):
    piece_index: int
    restored_content: str
    version_number: int


class ContentScoreRequest(BaseModel):
    content_override: Optional[str] = None


class ContentScoreResponse(BaseModel):
    overall: int = Field(ge=0, le=100)
    readability: int = Field(ge=0, le=100)
    brand_alignment: int = Field(ge=0, le=100)
    engagement_potential: int = Field(ge=0, le=100)
    clarity: int = Field(ge=0, le=100)
    audience_fit: int = Field(ge=0, le=100)
    reasoning: str


class SuggestionItem(BaseModel):
    title: str
    description: str
    instruction: str


class SuggestionsResponse(BaseModel):
    suggestions: list[SuggestionItem]


class BatchChatRequest(BaseModel):
    instruction: str = Field(min_length=1)
    piece_indices: list[int] = Field(min_length=1)
    context: Optional[str] = None
    include_score: bool = False


class BatchChatResult(BaseModel):
    piece_index: int
    status: str
    message_id: Optional[str] = None
    revised_content: Optional[str] = None
    error: Optional[str] = None


class BatchChatSummary(BaseModel):
    total: int
    succeeded: int
    failed: int


class BatchChatResponse(BaseModel):
    results: list[BatchChatResult]
    summary: BatchChatSummary


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


def _ensure_piece(campaign: Campaign, piece_index: int):
    if campaign.content is None or piece_index < 0 or piece_index >= len(campaign.content.pieces):
        raise HTTPException(status_code=422, detail="piece_index is out of range")
    return campaign.content.pieces[piece_index]


async def _next_version_number(chat_store: ContentChatStore, campaign_id: str, piece_index: int) -> int:
    all_messages, _ = await chat_store.get_history(campaign_id, piece_index, limit=2000, offset=0)
    non_reverted_assistant_count = sum(
        1
        for m in all_messages
        if m.role == "assistant" and not bool((m.metadata or {}).get("reverted", False))
    )
    return non_reverted_assistant_count + 1


def _score_prompt(campaign: Campaign, content_to_score: str) -> list[dict[str, str]]:
    strategy = campaign.strategy
    tone = campaign.content.tone_of_voice if campaign.content is not None else ""
    strategy_block = strategy.model_dump() if strategy is not None else {}
    prompt = (
        "You are a senior marketing reviewer. Score the content from 0-100 in each dimension.\n"
        "Return ONLY valid JSON with keys:\n"
        "overall, readability, brand_alignment, engagement_potential, clarity, audience_fit, reasoning.\n\n"
        f"Campaign strategy: {strategy_block}\n"
        f"Target audience: {strategy.target_audience.model_dump() if strategy is not None else {}}\n"
        f"Tone of voice: {tone}\n"
        f"Brand guidelines / constraints: {campaign.brief.additional_context}\n\n"
        f"Content:\n{content_to_score}"
    )
    return [{"role": "user", "content": prompt}]


def _suggestions_prompt(campaign: Campaign, piece_content: str) -> list[dict[str, str]]:
    strategy = campaign.strategy
    tone = campaign.content.tone_of_voice if campaign.content is not None else ""
    prompt = (
        "You are an expert marketing copy coach.\n"
        "Return JSON only in this format:\n"
        '{"suggestions":[{"title":"...","description":"...","instruction":"..."}]}\n'
        "Provide 2-3 actionable improvements.\n\n"
        f"Campaign strategy: {strategy.model_dump() if strategy is not None else {}}\n"
        f"Target audience: {strategy.target_audience.model_dump() if strategy is not None else {}}\n"
        f"Tone of voice: {tone}\n"
        f"Content:\n{piece_content}"
    )
    return [{"role": "user", "content": prompt}]


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON from model: {exc}") from exc


@router.post("/content/{piece_index}/chat", response_model=ContentChatPostResponse | ContentChatStreamAcceptedResponse)
@limiter.limit("30/minute")
async def chat_with_content_piece(
    request: Request,
    response: Response,
    campaign_id: str,
    piece_index: int,
    background_tasks: BackgroundTasks,
    body: ContentChatRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_chat_write),
    user: Optional[User] = Depends(get_current_user),
) -> ContentChatPostResponse | ContentChatStreamAcceptedResponse:
    piece = _ensure_piece(campaign, piece_index)
    before_content = piece.human_edited_content or piece.content
    system_prompt = _build_system_prompt(campaign, piece_index, before_content, body.context)

    chat_store = get_content_chat_store()
    recent_messages, _ = await chat_store.get_history(campaign.id, piece_index, limit=20, offset=0)
    llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in recent_messages:
        llm_messages.append({"role": msg.role, "content": msg.content})
    llm_messages.append({"role": "user", "content": body.instruction})

    user_msg = await chat_store.create_message(
        campaign_id=campaign.id,
        piece_index=piece_index,
        role="user",
        content=body.instruction,
        user_id=user.id if user else None,
        metadata={"context": body.context or "", "include_score": body.include_score, "stream": body.stream},
    )

    if body.stream:
        response.status_code = 202

        async def _run_stream() -> None:
            full_content = ""
            try:
                llm_service = get_llm_service()
                async for token in llm_service.chat_stream(llm_messages):
                    full_content += token
                    await manager.broadcast(
                        {
                            "type": "chat_stream",
                            "campaign_id": campaign.id,
                            "piece_index": piece_index,
                            "message_id": user_msg.id,
                            "token": token,
                        }
                    )

                version_number = await _next_version_number(chat_store, campaign.id, piece_index)
                await chat_store.create_message(
                    campaign_id=campaign.id,
                    piece_index=piece_index,
                    role="assistant",
                    content=full_content,
                    user_id=None,
                    metadata={
                        "instruction_message_id": user_msg.id,
                        "version": {
                            "before": before_content,
                            "after": full_content,
                            "version_number": version_number,
                        },
                        "include_score": body.include_score,
                    },
                )
                await manager.broadcast(
                    {
                        "type": "chat_stream_end",
                        "campaign_id": campaign.id,
                        "piece_index": piece_index,
                        "message_id": user_msg.id,
                        "full_content": full_content,
                    }
                )
            except Exception as exc:
                logger.exception("Streaming chat failed for campaign=%s piece=%d", campaign.id, piece_index)
                await manager.broadcast(
                    {
                        "type": "chat_stream_error",
                        "campaign_id": campaign.id,
                        "piece_index": piece_index,
                        "message_id": user_msg.id,
                        "error": str(exc),
                    }
                )

        background_tasks.add_task(_run_stream)
        return ContentChatStreamAcceptedResponse(message_id=user_msg.id, status="streaming")

    revised_content = await get_llm_service().chat(llm_messages)
    version_number = await _next_version_number(chat_store, campaign.id, piece_index)
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


@router.get("/content/{piece_index}/chat", response_model=ContentChatHistoryResponse)
async def get_content_chat_history(
    campaign_id: str,
    piece_index: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    campaign: Campaign = Depends(get_campaign_for_chat_read),
) -> ContentChatHistoryResponse:
    _ensure_piece(campaign, piece_index)
    messages, total = await get_content_chat_store().get_history(
        campaign_id=campaign.id,
        piece_index=piece_index,
        limit=limit,
        offset=offset,
    )
    return ContentChatHistoryResponse(messages=messages, total=total)


@router.post("/content/{piece_index}/chat/revert", response_model=RevertResponse)
@limiter.limit("20/minute")
async def revert_content_chat_version(
    request: Request,
    response: Response,
    campaign_id: str,
    piece_index: int,
    campaign: Campaign = Depends(get_campaign_for_chat_write),
    campaign_store: CampaignStore = Depends(get_campaign_store),
) -> RevertResponse:
    _ensure_piece(campaign, piece_index)
    chat_store = get_content_chat_store()
    last_assistant = await chat_store.get_last_non_reverted_assistant_message(campaign.id, piece_index)
    if last_assistant is None:
        raise HTTPException(status_code=409, detail="No AI edits to revert")

    version_meta = (last_assistant.metadata or {}).get("version", {})
    before_value = version_meta.get("before")
    if before_value is None:
        raise HTTPException(status_code=409, detail="No AI edits to revert")

    for attempt in range(2):
        try:
            fresh = await campaign_store.get(campaign.id)
            if fresh is None:
                raise HTTPException(status_code=404, detail="Campaign not found")
            piece = _ensure_piece(fresh, piece_index)
            piece.human_edited_content = str(before_value)
            await campaign_store.update(fresh)
            break
        except ConcurrentUpdateError:
            if attempt == 1:
                raise HTTPException(status_code=409, detail="Concurrent update conflict, please retry")
            await asyncio.sleep(0.1)

    metadata = dict(last_assistant.metadata or {})
    metadata["reverted"] = True
    await chat_store.update_message_metadata(last_assistant.id, metadata)
    return RevertResponse(
        piece_index=piece_index,
        restored_content=str(before_value),
        version_number=int(version_meta.get("version_number", 0)),
    )


@router.get("/content/{piece_index}/chat/versions", response_model=ContentVersionsResponse)
async def get_content_chat_versions(
    campaign_id: str,
    piece_index: int,
    campaign: Campaign = Depends(get_campaign_for_chat_read),
) -> ContentVersionsResponse:
    piece = _ensure_piece(campaign, piece_index)
    history, _ = await get_content_chat_store().get_history(campaign.id, piece_index, limit=5000, offset=0)
    versions: list[ContentVersionItem] = [
        ContentVersionItem(
            version_number=1,
            content=piece.content,
            created_at=campaign.created_at,
            message_id=None,
        )
    ]
    next_version = 2
    for message in history:
        if message.role != "assistant":
            continue
        metadata = message.metadata or {}
        if bool(metadata.get("reverted", False)):
            continue
        version = metadata.get("version", {})
        after = version.get("after")
        if after is None:
            continue
        versions.append(
            ContentVersionItem(
                version_number=int(version.get("version_number", next_version)),
                content=str(after),
                created_at=message.created_at,
                message_id=message.id,
            )
        )
        next_version += 1
    return ContentVersionsResponse(versions=versions)


@router.post("/content/{piece_index}/chat/score", response_model=ContentScoreResponse)
@limiter.limit("20/minute")
async def score_content_piece(
    request: Request,
    response: Response,
    campaign_id: str,
    piece_index: int,
    body: ContentScoreRequest = Body(default=ContentScoreRequest()),
    campaign: Campaign = Depends(get_campaign_for_chat_write),
    llm_service: LLMService = Depends(get_llm_service),
) -> ContentScoreResponse:
    piece = _ensure_piece(campaign, piece_index)
    content_to_score = body.content_override or piece.human_edited_content or piece.content
    messages = _score_prompt(campaign, content_to_score)

    last_error: Optional[Exception] = None
    for _ in range(2):
        try:
            raw = await llm_service.chat_json(messages)
            data = _parse_json(raw)
            score = ContentScoreResponse(**data)
            return score
        except Exception as exc:
            last_error = exc
            continue
    raise HTTPException(status_code=502, detail=f"Unable to produce valid score response: {last_error}")


@router.get("/content/{piece_index}/chat/suggestions", response_model=SuggestionsResponse)
@limiter.limit("10/minute")
async def get_content_suggestions(
    request: Request,
    response: Response,
    campaign_id: str,
    piece_index: int,
    refresh: bool = Query(default=False),
    campaign: Campaign = Depends(get_campaign_for_chat_read),
    llm_service: LLMService = Depends(get_llm_service),
) -> SuggestionsResponse:
    piece = _ensure_piece(campaign, piece_index)
    chat_store = get_content_chat_store()

    if not refresh:
        cached = await chat_store.get_suggestions_message(campaign.id, piece_index)
        if cached is not None:
            metadata = cached.metadata or {}
            if isinstance(metadata.get("suggestions"), list):
                return SuggestionsResponse(suggestions=[SuggestionItem(**s) for s in metadata["suggestions"]])
            try:
                payload = _parse_json(cached.content)
                return SuggestionsResponse(suggestions=[SuggestionItem(**s) for s in payload.get("suggestions", [])])
            except Exception:
                logger.debug("Cached suggestions message had invalid JSON, regenerating")

    raw = await llm_service.chat_json(_suggestions_prompt(campaign, piece.human_edited_content or piece.content))
    payload = _parse_json(raw)
    suggestions = [SuggestionItem(**s) for s in payload.get("suggestions", [])]
    await chat_store.create_message(
        campaign_id=campaign.id,
        piece_index=piece_index,
        role="system",
        content=json.dumps({"suggestions": [s.model_dump() for s in suggestions]}),
        metadata={"type": "suggestions", "suggestions": [s.model_dump() for s in suggestions]},
    )
    return SuggestionsResponse(suggestions=suggestions)


@router.post("/content/batch-chat", response_model=BatchChatResponse)
@limiter.limit("5/minute")
async def batch_chat_content_pieces(
    request: Request,
    response: Response,
    campaign_id: str,
    body: BatchChatRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_chat_write),
    user: Optional[User] = Depends(get_current_user),
) -> BatchChatResponse:
    if campaign.content is None:
        raise HTTPException(status_code=422, detail="piece_index is out of range")

    invalid = [idx for idx in body.piece_indices if idx < 0 or idx >= len(campaign.content.pieces)]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid piece_indices: {invalid}")

    semaphore = asyncio.Semaphore(3)
    chat_store = get_content_chat_store()
    llm_service = get_llm_service()

    async def _process(piece_index: int) -> BatchChatResult:
        async with semaphore:
            try:
                piece = campaign.content.pieces[piece_index]
                before_content = piece.human_edited_content or piece.content
                llm_messages: list[dict[str, str]] = [
                    {"role": "system", "content": _build_system_prompt(campaign, piece_index, before_content, body.context)},
                    {"role": "user", "content": body.instruction},
                ]
                revised = await llm_service.chat(llm_messages)
                user_msg = await chat_store.create_message(
                    campaign_id=campaign.id,
                    piece_index=piece_index,
                    role="user",
                    content=body.instruction,
                    user_id=user.id if user else None,
                    metadata={"context": body.context or "", "include_score": body.include_score, "batch": True},
                )
                version_number = await _next_version_number(chat_store, campaign.id, piece_index)
                assistant_msg = await chat_store.create_message(
                    campaign_id=campaign.id,
                    piece_index=piece_index,
                    role="assistant",
                    content=revised,
                    user_id=None,
                    metadata={
                        "instruction_message_id": user_msg.id,
                        "version": {
                            "before": before_content,
                            "after": revised,
                            "version_number": version_number,
                        },
                        "include_score": body.include_score,
                        "batch": True,
                    },
                )
                return BatchChatResult(
                    piece_index=piece_index,
                    status="success",
                    message_id=assistant_msg.id,
                    revised_content=revised,
                )
            except Exception as exc:
                logger.exception("Batch chat failed for campaign=%s piece=%d", campaign.id, piece_index)
                return BatchChatResult(piece_index=piece_index, status="failed", error=str(exc))

    results = await asyncio.gather(*(_process(idx) for idx in body.piece_indices))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    return BatchChatResponse(
        results=results,
        summary=BatchChatSummary(total=len(results), succeeded=succeeded, failed=failed),
    )
