import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class MediaConfirmRequest(BaseModel):
    event_id: uuid.UUID
    idempotency_key: str
    r2_object_key: str
    r2_upload_id: str | None = None

class MediaConfirmResponse(BaseModel):
    status: str
    message: str

class MediaResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    uploaded_by: uuid.UUID | None = None
    guest_session_id: uuid.UUID | None = None
    type: str | None = None
    r2_object_key: str
    status: str | None = None
    file_size_bytes: int | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    thumbnail_url: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
