import uuid
from pydantic import BaseModel, Field

class UploadPresignFile(BaseModel):
    client_file_id: str
    file_name: str
    file_size_bytes: int
    mime_type: str
    checksum: str | None = None

class UploadPresignRequest(BaseModel):
    event_id: uuid.UUID
    files: list[UploadPresignFile]

class PresignedChunk(BaseModel):
    part_number: int
    url: str

class PresignFileResponse(BaseModel):
    client_file_id: str
    r2_upload_id: str | None = None
    r2_object_key: str
    idempotency_key: str
    chunk_size_bytes: int | None = None
    chunks: list[PresignedChunk]

class UploadPresignResponse(BaseModel):
    files: list[PresignFileResponse]
