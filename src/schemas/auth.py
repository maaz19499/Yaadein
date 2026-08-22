import uuid
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class UserProfileResponse(BaseSchema):
    id: uuid.UUID
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    plan: str = "starter"
    events_created: int = 0


class UserProfileUpdate(BaseSchema):
    name: str | None = None
    avatar_url: str | None = None
