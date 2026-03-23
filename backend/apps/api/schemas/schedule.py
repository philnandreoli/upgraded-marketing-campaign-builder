"""
Pydantic request/response schemas for campaign scheduling API endpoints.
"""

from __future__ import annotations

from datetime import date, time
from typing import Optional

from pydantic import BaseModel

from backend.models.campaign import ContentPiece


class SchedulePieceRequest(BaseModel):
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    platform_target: Optional[str] = None


class PieceSchedule(BaseModel):
    piece_index: int
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    platform_target: Optional[str] = None


class BulkScheduleRequest(BaseModel):
    schedules: list[PieceSchedule]


class CalendarPiece(BaseModel):
    piece_index: int
    piece: ContentPiece


class CalendarDayGroup(BaseModel):
    date: date
    pieces: list[CalendarPiece]


class CalendarResponse(BaseModel):
    scheduled: list[CalendarDayGroup]
    unscheduled: list[CalendarPiece]
