"""
Campaign content scheduling routes.

Endpoints:
  PATCH /api/workspaces/{workspace_id}/campaigns/{campaign_id}/content/{piece_index}/schedule
      — Set/clear scheduling metadata for a single content piece
  POST  /api/workspaces/{workspace_id}/campaigns/{campaign_id}/content/bulk-schedule
      — Atomically schedule multiple content pieces in one request
  GET   /api/workspaces/{workspace_id}/campaigns/{campaign_id}/calendar
      — Return content grouped by scheduled date plus unscheduled items
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.apps.api.dependencies import (
    get_campaign_for_read,
    get_campaign_for_write,
    get_campaign_store,
)
from backend.apps.api.schemas.schedule import (
    BulkScheduleRequest,
    CalendarDayGroup,
    CalendarPiece,
    CalendarResponse,
    SchedulePieceRequest,
)
from backend.core.exceptions import ConcurrentUpdateError
from backend.models.campaign import Campaign, ContentPiece

router = APIRouter(tags=["campaign-schedule"])


def _get_piece_or_400(campaign: Campaign, piece_index: int) -> ContentPiece:
    if campaign.content is None or piece_index < 0 or piece_index >= len(campaign.content.pieces):
        raise HTTPException(status_code=400, detail="piece_index is out of range")
    return campaign.content.pieces[piece_index]


@router.patch("/campaigns/{campaign_id}/content/{piece_index}/schedule", response_model=ContentPiece)
async def schedule_piece(
    piece_index: int,
    body: SchedulePieceRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
) -> ContentPiece:
    piece = _get_piece_or_400(campaign, piece_index)
    piece.scheduled_date = body.scheduled_date
    piece.scheduled_time = body.scheduled_time
    piece.platform_target = body.platform_target

    try:
        await get_campaign_store().update(campaign)
    except ConcurrentUpdateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return piece


@router.post("/campaigns/{campaign_id}/content/bulk-schedule", response_model=CalendarResponse)
async def bulk_schedule(
    body: BulkScheduleRequest = Body(),
    campaign: Campaign = Depends(get_campaign_for_write),
) -> CalendarResponse:
    # Validate ALL piece_index values before applying any changes (atomic)
    for item in body.schedules:
        _get_piece_or_400(campaign, item.piece_index)

    # Apply all schedule changes
    for item in body.schedules:
        piece = campaign.content.pieces[item.piece_index]
        piece.scheduled_date = item.scheduled_date
        piece.scheduled_time = item.scheduled_time
        piece.platform_target = item.platform_target

    try:
        await get_campaign_store().update(campaign)
    except ConcurrentUpdateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Return calendar-format response
    return _build_calendar_response(campaign)


def _build_calendar_response(campaign: Campaign) -> CalendarResponse:
    if campaign.content is None:
        return CalendarResponse(scheduled=[], unscheduled=[])

    scheduled_by_day: dict[date, list[CalendarPiece]] = defaultdict(list)
    unscheduled: list[CalendarPiece] = []

    for idx, piece in enumerate(campaign.content.pieces):
        cal_piece = CalendarPiece(piece_index=idx, piece=piece)
        if piece.scheduled_date is None:
            unscheduled.append(cal_piece)
        else:
            scheduled_by_day[piece.scheduled_date].append(cal_piece)

    scheduled = [
        CalendarDayGroup(date=scheduled_date, pieces=scheduled_by_day[scheduled_date])
        for scheduled_date in sorted(scheduled_by_day.keys())
    ]

    return CalendarResponse(scheduled=scheduled, unscheduled=unscheduled)


@router.get("/campaigns/{campaign_id}/calendar", response_model=CalendarResponse)
async def get_calendar(
    campaign: Campaign = Depends(get_campaign_for_read),
) -> CalendarResponse:
    return _build_calendar_response(campaign)
