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
async def generate_presigned_urls(
    payload: UploadPresignRequest,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> UploadPresignResponse:
    # 1. Authorize access to event
    if identity.user_id:
        # Standard user check (host/admin)
        event_res = await db.execute(select(Event).where(Event.id == payload.event_id))
        event = event_res.scalar_one_or_none()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found.",
            )
        # Check ownership (unless admin)
        # We need to fetch the user to check role, or check if we can query it
        # Actually, get_upload_identity has already validated the user is in public.users
        from src.models.user import User
        user_res = await db.execute(select(User).where(User.id == identity.user_id))
        user = user_res.scalar_one()
        if event.host_id != identity.user_id and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to upload to this event.",
            )
    elif identity.guest_session_id:
        # Guest user check: Must match the event in headers
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
        _, ext = os.path.splitext(file.file_name)
        object_key = f"events/{payload.event_id}/originals/{file.client_file_id}{ext}"
        
        # Calculate unique idempotency key
        unique_str = f"{payload.event_id}-{file.client_file_id}-{identity.guest_session_id or identity.user_id}"
        idempotency_key = f"idem-{hashlib.md5(unique_str.encode()).hexdigest()}"
        
        chunk_size_limit = 10 * 1024 * 1024  # 10MB

        if file.file_size_bytes > chunk_size_limit:
            # Multipart upload presigning
            upload_id, part_urls = storage_service.generate_presigned_multipart_upload_urls(
                object_key=object_key,
                file_size=file.file_size_bytes,
            )
            chunks = [PresignedChunk(part_number=p["part_number"], url=p["url"]) for p in part_urls]
            
            files_response.append(
                PresignFileResponse(
                    client_file_id=file.client_file_id,
                    r2_upload_id=upload_id,
                    r2_object_key=object_key,
                    idempotency_key=idempotency_key,
                    chunk_size_bytes=chunk_size_limit,
                    chunks=chunks,
                )
            )
        else:
            # Single-part upload presigning
            url = storage_service.generate_presigned_upload_url(object_key)
            chunks = [PresignedChunk(part_number=1, url=url)]
            
            files_response.append(
                PresignFileResponse(
                    client_file_id=file.client_file_id,
                    r2_upload_id=None,
                    r2_object_key=object_key,
                    idempotency_key=idempotency_key,
                    chunk_size_bytes=None,
                    chunks=chunks,
                )
            )

    return UploadPresignResponse(files=files_response)
