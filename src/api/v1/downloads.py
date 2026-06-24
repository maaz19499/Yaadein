import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.api.deps import get_db, get_upload_identity, UploadIdentity
from src.config import settings
from src.models.event import Event
from src.models.media import Media, Export
from src.models.user import User
from src.services.storage import R2StorageService

router = APIRouter()


class ExportRequest(BaseModel):
    scope: str  # Options: 'full_event', 'album'
    album_id: uuid.UUID | None = None


class ExportResponse(BaseModel):
    export_id: uuid.UUID
    status: str


class ExportStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    download_url: str | None = None


@router.get("/media/{event_id}/{media_id}/download")
async def download_media(
    event_id: uuid.UUID,
    media_id: uuid.UUID,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
):
    # 1. Authorize identity (if guest, verify event matches header)
    if identity.guest_session_id:
        if identity.event_id != event_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access downloads for this event.",
            )

    # 2. Fetch Media
    media_res = await db.execute(
        select(Media).where(Media.event_id == event_id, Media.id == media_id)
    )
    media = media_res.scalar_one_or_none()
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found.",
        )

    # 3. Fetch Event
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # 4. Check limits based on plan
    limits = settings.PLAN_LIMITS.get(event.plan) or settings.PLAN_LIMITS.get("default")
    max_count = limits.get("max_count")
    max_size_bytes = limits.get("max_size_bytes")

    # Enforce count-based limit
    if max_count is not None:
        count_res = await db.execute(
            select(func.count())
            .select_from(Media)
            .where(Media.event_id == event_id, Media.created_at < media.created_at)
        )
        count_prior = count_res.scalar() or 0
        if count_prior >= max_count:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "DOWNLOAD_LOCKED",
                    "message": "Event storage limit exceeded. Ask the host to upgrade their plan to unlock high-resolution downloads.",
                },
            )

    # Enforce size-based limit
    if max_size_bytes is not None:
        size_res = await db.execute(
            select(func.sum(Media.file_size_bytes)).where(
                Media.event_id == event_id, Media.created_at < media.created_at
            )
        )
        size_prior = size_res.scalar() or 0
        if size_prior >= max_size_bytes:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "DOWNLOAD_LOCKED",
                    "message": "Event storage limit exceeded. Ask the host to upgrade their plan to unlock high-resolution downloads.",
                },
            )

    # 5. Generate presigned download URL
    storage_service = R2StorageService()
    try:
        download_url = storage_service.generate_presigned_download_url(
            media.r2_object_key, expires_in=300
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate presigned download URL: {str(e)}",
        )

    return RedirectResponse(
        url=download_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


@router.post(
    "/events/{event_id}/exports",
    response_model=ExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_zip_export(
    event_id: uuid.UUID,
    payload: ExportRequest,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
):
    # 1. User must be authenticated (no guests allowed to trigger exports)
    if not identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for exports.",
        )

    # 2. Verify Event exists
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # 3. Authorize Host / Admin
    user_res = await db.execute(select(User).where(User.id == identity.user_id))
    user = user_res.scalar_one()
    if event.host_id != identity.user_id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to trigger exports for this event.",
        )

    # 4. Insert Export record
    new_export = Export(
        event_id=event_id,
        requested_by=identity.user_id,
        scope=payload.scope,
        status="queued",
    )
    db.add(new_export)
    await db.flush()

    # 5. Dispatch Celery task
    from src.workers.tasks.media import generate_zip_export

    album_id_str = str(payload.album_id) if payload.album_id else None
    generate_zip_export.delay(
        str(new_export.id), str(event_id), payload.scope, album_id_str
    )

    await db.commit()

    return ExportResponse(export_id=new_export.id, status="queued")


@router.get(
    "/events/{event_id}/exports/{export_id}", response_model=ExportStatusResponse
)
async def get_export_status(
    event_id: uuid.UUID,
    export_id: uuid.UUID,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
):
    # 1. User must be authenticated
    if not identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for exports.",
        )

    # 2. Verify Event exists
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # 3. Authorize Host / Admin
    user_res = await db.execute(select(User).where(User.id == identity.user_id))
    user = user_res.scalar_one()
    if event.host_id != identity.user_id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view exports for this event.",
        )

    # 4. Fetch Export record
    export_res = await db.execute(
        select(Export).where(Export.event_id == event_id, Export.id == export_id)
    )
    export_rec = export_res.scalar_one_or_none()
    if not export_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export record not found.",
        )

    # If the export is ready, we make sure the URL is valid by dynamically regenerating it or returning the stored one
    # To be safe, if there's an export key, we regenerate it to prevent expiration issues
    download_url = export_rec.download_url
    if export_rec.status == "ready":
        storage_service = R2StorageService()
        export_key = f"events/{event_id}/exports/{export_id}.zip"
        try:
            download_url = storage_service.generate_presigned_download_url(
                export_key, expires_in=86400
            )
        except Exception:
            pass

    return ExportStatusResponse(
        id=export_rec.id, status=export_rec.status, download_url=download_url
    )
