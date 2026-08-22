import uuid
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class UploadPresignFile(BaseSchema):
    client_file_id: str | None = None
    filename: str | None = None
    file_name: str | None = None
    file_size_bytes: int | None = None
    size_bytes: int | None = None
    mime_type: str | None = "image/jpeg"
    checksum: str | None = None


class UploadPresignRequest(BaseSchema):
    event_id: uuid.UUID
    files: list[UploadPresignFile]


class PresignedChunk(BaseSchema):
    part_number: int
    url: str


class PresignFileResponse(BaseSchema):
    client_file_id: str | None = None
    file_id: str | None = None
    r2_upload_id: str | None = None
    upload_id: str | None = None
    r2_object_key: str | None = None
    idempotency_key: str
    chunk_size_bytes: int | None = None
    chunk_size: int | None = None
    confirm_url: str = "/api/v1/media/confirm-upload"
    part_urls: list[str] = []
    chunks: list[PresignedChunk] = []


class UploadPresignResponse(BaseSchema):
    files: list[PresignFileResponse] = []
    uploads: list[PresignFileResponse] = []
