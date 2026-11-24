"""Pydantic schema for live WebSocket office activity events."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class OfficeEvent(BaseModel):
    event_id: str
    experiment_id: str
    timestamp: str
    event_type: str
    agent_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
