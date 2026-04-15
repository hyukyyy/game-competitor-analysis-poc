from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawGame(BaseModel):
    platform: str
    external_id: str
    payload: dict[str, Any]
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class RawReview(BaseModel):
    platform: str
    external_id: str
    review_id: str
    text: str | None = None
    rating: int | None = None
    posted_at: datetime | None = None


class NormalizedGame(BaseModel):
    platform: str
    external_id: str
    title: str | None = None
    description: str | None = None
    raw_tags: list[str] = Field(default_factory=list)
