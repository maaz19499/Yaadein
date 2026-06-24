import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict


class AlbumCreate(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., pattern="^(static|dynamic)$")
    media_ids: list[uuid.UUID] | None = None
    dynamic_filters: dict[str, Any] | None = None


class AlbumResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    type: str
    dynamic_filters: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
