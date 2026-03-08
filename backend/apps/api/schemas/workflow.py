"""
Pydantic request/response schemas for campaign workflow API endpoints.

These schemas are shared across campaign route modules:
  - campaigns.py (CRUD and user-profile routes)
  - campaign_workflow.py (workflow command routes)
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Workflow response DTOs
# ---------------------------------------------------------------------------

class WorkflowActionResponse(BaseModel):
    campaign_id: str
    message: str


class PieceDecisionResponse(BaseModel):
    campaign_id: str
    piece_index: int
    approval_status: str
    message: str


class PieceNotesResponse(BaseModel):
    campaign_id: str
    piece_index: int
    message: str


# ---------------------------------------------------------------------------
# Workflow request models
# ---------------------------------------------------------------------------

class PieceDecisionRequest(BaseModel):
    approved: bool
    edited_content: Optional[str] = None
    notes: str = ""


class UpdatePieceNotesRequest(BaseModel):
    notes: str
