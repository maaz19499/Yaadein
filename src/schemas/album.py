from datetime import datetime
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class AlbumCreate(BaseSchema):
    name: str = Field(..., min_length=1)
    type: str = Field("static", pattern="^(static|dynamic)$")
    media_ids: list[uuid.UUID] | None = None
    dynamic_filters: dict[str, Any] | None = None


class AlbumResponse(BaseSchema):
    id: uuid.UUID
    event_id: uuid.UUID | None = None
    name: str
    type: str = "static"
    emoji: str = "📁"
    media_count: int = 0
    dynamic_filters: dict[str, Any] | None = None
    created_at: datetime | None = None
