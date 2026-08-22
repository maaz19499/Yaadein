import hashlib
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_upload_identity, UploadIdentity
from src.models.event import Event
from src.schemas.upload import (
    UploadPresignRequest,
    UploadPresignResponse,
    PresignFileResponse,
    PresignedChunk,
)
from src.services.storage import R2StorageService

router = APIRouter(tags=["uploads"])


@router.post("/presign", response_model=UploadPresignResponse)
@router.post("/presigned-urls", response_model=UploadPresignResponse)
async def generate_presigned_urls(
    payload: UploadPresignRequest,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> UploadPresignResponse:
    # 1. Authorize access to event
    if identity.user_id:
        event_res = await db.execute(select(Event).where(Event.id == payload.event_id))
        event = event_res.scalar_one_or_none()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found.",
            )
        from src.models.user import User

        user_res = await db.execute(select(User).where(User.id == identity.user_id))
        user = user_res.scalar_one_or_none()
        if user and event.host_id != identity.user_id and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to upload to this event.",
            )
    elif identity.guest_session_id:
        if payload.event_id != identity.event_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="X-Event-ID header does not match the event_id in payload.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized identity.",
        )

    storage_service = R2StorageService()
    files_response = []

    for file in payload.files:
        file_name = file.filename or file.file_name or "upload.jpg"
        file_size = file.size_bytes or file.file_size_bytes or (5 * 1024 * 1024)
        client_id = file.client_file_id or f"file_{uuid.uuid4().hex[:10]}"

        _, ext = os.path.splitext(file_name)
        if not ext:
            ext = ".jpg"
        object_key = f"events/{payload.event_id}/originals/{client_id}{ext}"

        # Calculate unique idempotency key
        unique_str = f"{payload.event_id}-{client_id}-{identity.guest_session_id or identity.user_id}"
        idempotency_key = f"idem-{hashlib.md5(unique_str.encode()).hexdigest()}"

        chunk_size_limit = 8 * 1024 * 1024  # 8MB chunk size to match frontend

        if file_size > chunk_size_limit:
            # Multipart upload presigning
            upload_id, part_urls = (
                storage_service.generate_presigned_multipart_upload_urls(
                    object_key=object_key,
                    file_size=file_size,
                )
            )
            chunks = [
                PresignedChunk(part_number=p["part_number"], url=p["url"])
                for p in part_urls
            ]
            part_url_strings = [p["url"] for p in part_urls]

            file_resp = PresignFileResponse(
                client_file_id=client_id,
                file_id=client_id,
                r2_upload_id=upload_id,
                upload_id=upload_id,
                r2_object_key=object_key,
                idempotency_key=idempotency_key,
                chunk_size_bytes=chunk_size_limit,
                chunk_size=chunk_size_limit,
                confirm_url="/api/v1/media/confirm-upload",
                part_urls=part_url_strings,
                chunks=chunks,
            )
            files_response.append(file_resp)
        else:
            # Single-part upload presigning
            url = storage_service.generate_presigned_upload_url(object_key)
            chunks = [PresignedChunk(part_number=1, url=url)]

            file_resp = PresignFileResponse(
                client_file_id=client_id,
                file_id=client_id,
                r2_upload_id=None,
                upload_id=None,
                r2_object_key=object_key,
                idempotency_key=idempotency_key,
                chunk_size_bytes=None,
                chunk_size=None,
                confirm_url="/api/v1/media/confirm-upload",
                part_urls=[url],
                chunks=chunks,
            )
            files_response.append(file_resp)

    return UploadPresignResponse(files=files_response, uploads=files_response)
