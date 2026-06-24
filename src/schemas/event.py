from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class EventCreate(BaseModel):
    slug: str
    face_search_enabled: bool = False
    is_wedding: bool = False


class EventUpdate(BaseModel):
    slug: str | None = None
    face_search_enabled: bool | None = None
    is_wedding: bool | None = None


class EventResponse(BaseModel):
    id: uuid.UUID
    host_id: uuid.UUID | None
    slug: str
    plan: str | None
    face_search_enabled: bool
    storage_expires_at: datetime | None
    is_wedding: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventPublicResponse(BaseModel):
    id: uuid.UUID
    slug: str
    face_search_enabled: bool
    is_wedding: bool
    plan: str | None

    model_config = ConfigDict(from_attributes=True)
