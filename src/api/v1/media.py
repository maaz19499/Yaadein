import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from botocore.exceptions import ClientError

from src.api.deps import get_db, get_upload_identity, UploadIdentity
from src.models.media import Media
from src.models.user import User
from src.models.event import Event
from src.schemas.media import MediaResponse, MediaConfirmRequest
from src.schemas.upload import UploadPresignRequest, UploadPresignResponse
from src.api.v1.uploads import generate_presigned_urls
from src.services.storage import R2StorageService

router = APIRouter(tags=["media"])


@router.post("/presigned-urls", response_model=UploadPresignResponse)
async def media_presigned_urls(
    payload: UploadPresignRequest,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> UploadPresignResponse:
    return await generate_presigned_urls(payload, identity, db)


@router.post(
    "/confirm",
    response_model=MediaResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@router.post(
    "/confirm-upload",
    response_model=MediaResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def confirm_media_upload(
    payload: MediaConfirmRequest,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> MediaResponse:
    # 1. Authorize access to event
    if identity.user_id:
        event_res = await db.execute(select(Event).where(Event.id == payload.event_id))
        event = event_res.scalar_one_or_none()
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found.",
            )
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

    # 2. Idempotency Check: check if record already exists
    existing_res = await db.execute(
        select(Media).where(
            Media.event_id == payload.event_id,
            Media.idempotency_key == payload.idempotency_key,
        )
    )
    existing_media = existing_res.scalar_one_or_none()
    if existing_media:
        return MediaResponse(
            id=existing_media.id,
            event_id=existing_media.event_id,
            uploaded_by=existing_media.uploaded_by,
            guest_session_id=existing_media.guest_session_id,
            type=existing_media.type or "photo",
            status=existing_media.status or "ready",
            url=f"https://cdn.yaadein.com/{existing_media.r2_object_key}" if existing_media.r2_object_key else None,
            thumbnail_url=existing_media.thumbnail_url or (f"https://cdn.yaadein.com/{existing_media.r2_object_key}" if existing_media.r2_object_key else None),
            r2_object_key=existing_media.r2_object_key,
            file_size_bytes=existing_media.file_size_bytes or 0,
            mime_type=existing_media.mime_type,
            width=existing_media.width,
            height=existing_media.height,
            duration_seconds=existing_media.duration_seconds,
            album_ids=[],
            created_at=existing_media.created_at,
        )

    # 3. Complete and verify upload in storage
    storage_service = R2StorageService()
    if payload.r2_upload_id:
        try:
            storage_service.complete_multipart_upload(
                payload.r2_object_key, payload.r2_upload_id
            )
        except ClientError:
            pass

    file_size_bytes = 0
    mime_type = "image/jpeg"
    checksum = ""

    try:
        head_data = storage_service.head_object(payload.r2_object_key)
        file_size_bytes = head_data.get("ContentLength", 0)
        mime_type = head_data.get("ContentType", "image/jpeg")
        checksum = head_data.get("ETag", "").strip('"')
    except Exception:
        pass

    _, ext = os.path.splitext(payload.r2_object_key)
    is_video = ext.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm")
    media_type = "video" if is_video else "photo"

    # 5. Create Database record
    new_media = Media(
        event_id=payload.event_id,
        uploaded_by=identity.user_id,
        guest_session_id=identity.guest_session_id,
        type=media_type,
        r2_object_key=payload.r2_object_key,
        idempotency_key=payload.idempotency_key,
        status="visible",
        file_size_bytes=file_size_bytes,
        mime_type=mime_type,
        checksum=checksum,
    )
    db.add(new_media)
    await db.flush()

    # 6. Dispatch processing task
    if media_type == "video":
        try:
            from src.workers.tasks.media import process_video_upload

            process_video_upload.delay(str(payload.event_id), str(new_media.id))
        except Exception:
            pass
    elif media_type in ("photo", "image"):
        try:
            from src.workers.tasks.media import process_image_upload

            process_image_upload.delay(str(payload.event_id), str(new_media.id))
        except Exception:
            pass

    await db.commit()
    await db.refresh(new_media)

    return MediaResponse(
        id=new_media.id,
        event_id=new_media.event_id,
        uploaded_by=new_media.uploaded_by,
        guest_session_id=new_media.guest_session_id,
        type=new_media.type or "photo",
        status=new_media.status or "ready",
        url=f"https://cdn.yaadein.com/{new_media.r2_object_key}",
        thumbnail_url=new_media.thumbnail_url or f"https://cdn.yaadein.com/{new_media.r2_object_key}",
        r2_object_key=new_media.r2_object_key,
        file_size_bytes=new_media.file_size_bytes or 0,
        mime_type=new_media.mime_type,
        width=new_media.width,
        height=new_media.height,
        duration_seconds=new_media.duration_seconds,
        album_ids=[],
        created_at=new_media.created_at,
    )


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: uuid.UUID,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> None:
    media_res = await db.execute(select(Media).where(Media.id == media_id))
    media = media_res.scalar_one_or_none()
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found.",
        )

    # Check ownership
    event_res = await db.execute(select(Event).where(Event.id == media.event_id))
    event = event_res.scalar_one_or_none()

    if identity.user_id:
        user_res = await db.execute(select(User).where(User.id == identity.user_id))
        user = user_res.scalar_one_or_none()
        if (
            event
            and event.host_id != identity.user_id
            and media.uploaded_by != identity.user_id
            and user
            and user.role != "admin"
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this media.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only event hosts can delete photos.",
        )

    await db.delete(media)
    await db.commit()
