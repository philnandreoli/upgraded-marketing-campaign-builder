"""
Content chat domain models.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ContentChatMessage(BaseModel):
    id: str
    campaign_id: str
    piece_index: int
    role: str  # "user", "assistant", "system"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    user_id: Optional[str] = None

