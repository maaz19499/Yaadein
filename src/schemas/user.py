import uuid
from pydantic import BaseModel, ConfigDict


class GuestCreate(BaseModel):
    guest_session_id: uuid.UUID
    name: str
    phone: str | None = None
    face_search_consent: bool


class GuestResponseData(BaseModel):
    guest_session_id: uuid.UUID
    name: str | None
    face_search_consent: bool

    model_config = ConfigDict(from_attributes=True)


class GuestResponse(BaseModel):
    status: str = "success"
    guest: GuestResponseData
