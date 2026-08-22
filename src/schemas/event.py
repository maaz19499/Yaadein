from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class EventCreate(BaseSchema):
    name: str | None = None
    type: str | None = None
    date: datetime | None = None
    city: str | None = None
    cover_photo_url: str | None = None
    plan: str = "starter"
    guest_pin: str | None = Field(default=None, max_length=4)
    enable_face_search: bool = False
    slug: str | None = None
    face_search_enabled: bool | None = None
    is_wedding: bool = False


class EventUpdate(BaseSchema):
    name: str | None = None
    type: str | None = None
    date: datetime | None = None
    city: str | None = None
    cover_photo_url: str | None = None
    status: str | None = None
    plan: str | None = None
    guest_pin: str | None = None
    enable_face_search: bool | None = None
    face_search_enabled: bool | None = None
    is_wedding: bool | None = None
    slug: str | None = None


class EventResponse(BaseSchema):
    id: uuid.UUID
    host_id: uuid.UUID | None = None
    slug: str
    name: str | None = None
    type: str | None = None
    date: datetime | None = None
    city: str | None = None
    cover_photo_url: str | None = None
    status: str = "pending"
    plan: str | None = "starter"
    photo_count: int = 0
    video_count: int = 0
    guest_count: int = 0
    storage_expires_at: datetime | None = None
    upload_expires_at: datetime | None = None
    expires_at: datetime | None = None
    face_clustered: bool = False
    face_search_enabled: bool = False
    enable_face_search: bool = False
    is_wedding: bool = False
    share_url: str | None = None
    guest_pin: str | None = None
    created_at: datetime


class EventPublicResponse(BaseSchema):
    id: uuid.UUID
    slug: str
    name: str | None = None
    type: str | None = None
    date: datetime | None = None
    city: str | None = None
    cover_photo_url: str | None = None
    status: str = "active"
    plan: str | None = None
    face_search_enabled: bool = False
    enable_face_search: bool = False
    is_wedding: bool = False
    share_url: str | None = None


class EventPinAuthRequest(BaseSchema):
    pin: str


class EventPinAuthResponse(BaseSchema):
    success: bool
    message: str | None = None


class EventQRResponse(BaseSchema):
    qr_url: str
    share_url: str
    whatsapp_url: str
