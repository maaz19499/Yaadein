import uuid
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class GuestCreate(BaseSchema):
    guest_session_id: uuid.UUID
    name: str
    phone: str | None = None
    face_search_consent: bool


class GuestResponseData(BaseSchema):
    guest_session_id: uuid.UUID
    name: str | None = None
    face_search_consent: bool


class GuestResponse(BaseSchema):
    status: str = "success"
    guest: GuestResponseData
