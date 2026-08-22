from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from src.schemas.album import AlbumResponse


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class MediaConfirmRequest(BaseSchema):
    event_id: uuid.UUID
    idempotency_key: str
    r2_object_key: str
    r2_upload_id: str | None = None
    face_consent: bool = False


class MediaConfirmResponse(BaseSchema):
    id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    status: str
    message: str | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    type: str | None = "photo"


class MediaResponse(BaseSchema):
    id: uuid.UUID
    event_id: uuid.UUID
    uploaded_by: uuid.UUID | None = None
    guest_session_id: uuid.UUID | None = None
    type: str = "photo"
    status: str = "ready"
    url: str | None = None
    thumbnail_url: str | None = None
    r2_object_key: str | None = None
    file_size_bytes: int | None = 0
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: int | None = None
    album_ids: list[str] = []
    face_embedding_id: str | None = None
    created_at: datetime


class GalleryResponse(BaseSchema):
    media: list[MediaResponse] = []
    albums: list[AlbumResponse] = []
    total_count: int = 0
    next_cursor: str | None = None


class FaceSearchResponse(BaseSchema):
    media_ids: list[uuid.UUID] = []
