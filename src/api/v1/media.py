import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from botocore.exceptions import ClientError

from src.api.deps import get_db, get_upload_identity, UploadIdentity
from src.models.media import Media
from src.models.user import User
from src.schemas.media import MediaConfirmRequest, MediaConfirmResponse
from src.services.storage import R2StorageService

router = APIRouter(tags=["media"])


@router.post("/confirm", response_model=MediaConfirmResponse, status_code=status.HTTP_202_ACCEPTED)
async def confirm_media_upload(
    payload: MediaConfirmRequest,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> MediaConfirmResponse:
    # 1. Authorize access to event
    from src.models.event import Event
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

    # 2. Idempotency Check: check if record already exists
    existing_res = await db.execute(
        select(Media).where(
            Media.event_id == payload.event_id,
            Media.idempotency_key == payload.idempotency_key,
        )
    )
    existing_media = existing_res.scalar_one_or_none()
    if existing_media:
        return MediaConfirmResponse(
            status=existing_media.status or "pending_verify",
            message="File already registered (idempotency match).",
        )

    # 3. Complete and verify upload in storage
    storage_service = R2StorageService()
    if payload.r2_upload_id:
        try:
            storage_service.complete_multipart_upload(payload.r2_object_key, payload.r2_upload_id)
        except ClientError:
            # If it failed to complete, maybe it was already completed
            # Let's log it or proceed to head_object check
            pass

    try:
        head_data = storage_service.head_object(payload.r2_object_key)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code in ("404", "NoSuchKey", "403"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File does not exist in R2 storage.",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage error: {str(e)}",
        )

    # 4. Extract metadata
    file_size_bytes = head_data.get("ContentLength")
    mime_type = head_data.get("ContentType")
    checksum = head_data.get("ETag", "").strip('"')

    _, ext = os.path.splitext(payload.r2_object_key)
    is_video = ext.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm")
    media_type = "video" if is_video else "image"

    # 5. Create Database record
    new_media = Media(
        event_id=payload.event_id,
        uploaded_by=identity.user_id,
        guest_session_id=identity.guest_session_id,
        type=media_type,
        r2_object_key=payload.r2_object_key,
        idempotency_key=payload.idempotency_key,
        status="pending_verify",
        file_size_bytes=file_size_bytes,
        mime_type=mime_type,
        checksum=checksum,
    )
    db.add(new_media)
    await db.flush()

    # 6. Dispatch processing task
    # We pass the parameters as strings to Celery for serialization safety
    if media_type == "image":
        from src.workers.tasks.media import process_image_upload
        process_image_upload.delay(str(payload.event_id), str(new_media.id))
    else:
        # Placeholder/stub for video processing or just mark it as visible or call a video task
        pass

    await db.commit()

    return MediaConfirmResponse(
        status="pending_verify",
        message="File registration initialized and processing task queued.",
    )
