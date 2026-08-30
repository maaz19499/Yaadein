from datetime import datetime, timedelta, timezone
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.models.album import Album
from src.models.event import Event
from src.models.guest import Guest
from src.models.media import Media
from src.models.face import FaceEmbedding
from src.models.user import User
from src.schemas.album import AlbumResponse
from src.schemas.event import (
    EventCreate,
    EventMediaStatsResponse,
    EventPinAuthRequest,
    EventPinAuthResponse,
    EventPublicResponse,
    EventQRResponse,
    EventResponse,
    EventUpdate,
    MediaCategoryStats,
)
from src.schemas.media import FaceSearchResponse, GalleryResponse, MediaResponse
from src.services.face import FaceEmbeddingService

router = APIRouter(tags=["events"])


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)


async def _get_event_counts(
    db: AsyncSession, event_id: uuid.UUID
) -> tuple[int, int, int]:
    """Get aggregated photo count, video count, and guest count for an event."""
    media_res = await db.execute(
        select(Media.type, func.count(Media.id))
        .where(Media.event_id == event_id, Media.status == "visible")
        .group_by(Media.type)
    )
    media_counts = dict(media_res.all())
    photo_count = media_counts.get("image", 0) + media_counts.get("photo", 0)
    video_count = media_counts.get("video", 0)

    guest_res = await db.execute(
        select(func.count(Guest.guest_session_id)).where(Guest.event_id == event_id)
    )
    guest_count = guest_res.scalar() or 0

    return photo_count, video_count, guest_count


def _build_event_response(
    event: Event,
    photo_count: int = 0,
    video_count: int = 0,
    guest_count: int = 0,
) -> EventResponse:
    face_search = bool(event.face_search_enabled)
    return EventResponse(
        id=event.id,
        host_id=event.host_id,
        slug=event.slug,
        name=event.name or event.slug,
        type=event.type or ("wedding" if event.is_wedding else "other"),
        date=event.date,
        city=event.city,
        cover_photo_url=event.cover_photo_url,
        status=event.status or "active",
        plan=event.plan or "starter",
        photo_count=photo_count,
        video_count=video_count,
        guest_count=guest_count,
        storage_expires_at=event.storage_expires_at,
        upload_expires_at=event.upload_expires_at,
        expires_at=event.storage_expires_at,
        face_clustered=event.face_clustered,
        face_search_enabled=face_search,
        enable_face_search=face_search,
        is_wedding=event.is_wedding,
        share_url=f"/e/{event.slug}",
        guest_pin=event.guest_pin,
        created_at=event.created_at,
    )


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_in: EventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    if current_user.role not in ("host", "photographer", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hosts, photographers, and admins can create events.",
        )

    # Determine slug
    if event_in.slug:
        slug = _slugify(event_in.slug)
    elif event_in.name:
        base_slug = _slugify(event_in.name)
        suffix = uuid.uuid4().hex[:6]
        slug = f"{base_slug}-{suffix}" if base_slug else f"event-{suffix}"
    else:
        slug = f"event-{uuid.uuid4().hex[:8]}"

    # Check for unique slug
    result = await db.execute(select(Event).where(Event.slug == slug))
    if result.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:4]}"

    now = datetime.now(timezone.utc)
    plan_tier = (event_in.plan or "starter").lower()
    
    # Expiry based on plan tier
    if plan_tier in ("starter", "free"):
        storage_days = 7
        upload_days = 3
        initial_status = "active"
    elif plan_tier == "basic":
        storage_days = 30
        upload_days = 7
        initial_status = "pending"
    elif plan_tier == "premium":
        storage_days = 90
        upload_days = 14
        initial_status = "pending"
    else:  # elite / professional
        storage_days = 365
        upload_days = 30
        initial_status = "pending"

    face_search = (
        event_in.enable_face_search
        if event_in.enable_face_search is not None
        else bool(event_in.face_search_enabled)
    )
    is_wedding = (
        event_in.is_wedding
        if event_in.is_wedding is not None
        else (event_in.type == "wedding")
    )

    event = Event(
        host_id=current_user.id,
        slug=slug,
        name=event_in.name,
        type=event_in.type or ("wedding" if is_wedding else "other"),
        date=event_in.date,
        city=event_in.city,
        cover_photo_url=event_in.cover_photo_url,
        status=initial_status,
        plan=plan_tier,
        face_search_enabled=face_search,
        storage_expires_at=now + timedelta(days=storage_days),
        upload_expires_at=now + timedelta(days=upload_days),
        is_wedding=is_wedding,
        guest_pin=event_in.guest_pin,
        created_at=now,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    return _build_event_response(event, 0, 0, 0)


@router.get("", response_model=list[EventResponse])
async def list_events(
    host_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EventResponse]:
    target_host_id = host_id if host_id is not None else current_user.id

    if target_host_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view events for this host.",
        )

    result = await db.execute(
        select(Event)
        .where(Event.host_id == target_host_id)
        .order_by(Event.created_at.desc())
    )
    events = list(result.scalars().all())

    responses = []
    for event in events:
        p_count, v_count, g_count = await _get_event_counts(db, event.id)
        responses.append(_build_event_response(event, p_count, v_count, g_count))

    return responses


@router.get("/slug/{slug}", response_model=EventPublicResponse)
async def get_event_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> EventPublicResponse:
    result = await db.execute(select(Event).where(Event.slug == slug))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )
    face_search = bool(event.face_search_enabled)
    return EventPublicResponse(
        id=event.id,
        slug=event.slug,
        name=event.name,
        type=event.type,
        date=event.date,
        city=event.city,
        cover_photo_url=event.cover_photo_url,
        status=event.status or "active",
        plan=event.plan,
        face_search_enabled=face_search,
        enable_face_search=face_search,
        is_wedding=event.is_wedding,
        share_url=f"/e/{event.slug}",
    )


@router.get("/{id_or_slug}", response_model=EventResponse)
async def get_event(
    id_or_slug: str,
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    event: Event | None = None
    try:
        event_uuid = uuid.UUID(id_or_slug)
        result = await db.execute(select(Event).where(Event.id == event_uuid))
        event = result.scalar_one_or_none()
    except ValueError:
        pass

    if not event:
        result = await db.execute(select(Event).where(Event.slug == id_or_slug))
        event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    p_count, v_count, g_count = await _get_event_counts(db, event.id)
    return _build_event_response(event, p_count, v_count, g_count)


def format_bytes(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


@router.get("/{id_or_slug}/stats", response_model=EventMediaStatsResponse)
@router.get("/{id_or_slug}/media-summary", response_model=EventMediaStatsResponse)
@router.get("/{id_or_slug}/storage-usage", response_model=EventMediaStatsResponse)
async def get_event_media_stats(
    id_or_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventMediaStatsResponse:
    event: Event | None = None
    try:
        event_uuid = uuid.UUID(id_or_slug)
        result = await db.execute(select(Event).where(Event.id == event_uuid))
        event = result.scalar_one_or_none()
    except ValueError:
        pass

    if not event:
        result = await db.execute(select(Event).where(Event.slug == id_or_slug))
        event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # Restrict access: only host of the event or admin can view host dashboard stats
    if event.host_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view storage statistics for this event.",
        )

    media_res = await db.execute(
        select(
            Media.type,
            func.count(Media.id),
            func.coalesce(func.sum(Media.file_size_bytes), 0),
        )
        .where(Media.event_id == event.id, Media.status == "visible")
        .group_by(Media.type)
    )
    rows = media_res.all()

    photo_count = 0
    photo_size = 0
    video_count = 0
    video_size = 0

    for media_type, count, size_bytes in rows:
        m_type = (media_type or "").lower()
        if m_type in ("photo", "image"):
            photo_count += count
            photo_size += int(size_bytes or 0)
        elif m_type == "video":
            video_count += count
            video_size += int(size_bytes or 0)

    total_count = photo_count + video_count
    total_size = photo_size + video_size

    return EventMediaStatsResponse(
        event_id=event.id,
        photos=MediaCategoryStats(
            count=photo_count,
            total_size_bytes=photo_size,
            total_size_formatted=format_bytes(photo_size),
        ),
        videos=MediaCategoryStats(
            count=video_count,
            total_size_bytes=video_size,
            total_size_formatted=format_bytes(video_size),
        ),
        total=MediaCategoryStats(
            count=total_count,
            total_size_bytes=total_size,
            total_size_formatted=format_bytes(total_size),
        ),
        photo_count=photo_count,
        photo_size_bytes=photo_size,
        video_count=video_count,
        video_size_bytes=video_size,
        total_count=total_count,
        total_size_bytes=total_size,
    )



@router.patch("/{id}", response_model=EventResponse)
@router.put("/{id}", response_model=EventResponse)
async def update_event(
    id: uuid.UUID,
    event_in: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    result = await db.execute(select(Event).where(Event.id == id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    if event.host_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this event.",
        )

    if event_in.name is not None:
        event.name = event_in.name
    if event_in.type is not None:
        event.type = event_in.type
    if event_in.date is not None:
        event.date = event_in.date
    if event_in.city is not None:
        event.city = event_in.city
    if event_in.cover_photo_url is not None:
        event.cover_photo_url = event_in.cover_photo_url
    if event_in.status is not None:
        event.status = event_in.status
    if event_in.plan is not None:
        event.plan = event_in.plan
    if event_in.guest_pin is not None:
        event.guest_pin = event_in.guest_pin

    if event_in.enable_face_search is not None:
        event.face_search_enabled = event_in.enable_face_search
    elif event_in.face_search_enabled is not None:
        event.face_search_enabled = event_in.face_search_enabled

    if event_in.is_wedding is not None:
        event.is_wedding = event_in.is_wedding

    if event_in.slug is not None and event_in.slug != event.slug:
        slug_check = await db.execute(select(Event).where(Event.slug == event_in.slug))
        if slug_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An event with this slug already exists.",
            )
        event.slug = event_in.slug

    db.add(event)
    await db.commit()
    await db.refresh(event)

    p_count, v_count, g_count = await _get_event_counts(db, event.id)
    return _build_event_response(event, p_count, v_count, g_count)


@router.get("/{event_id}/qr", response_model=EventQRResponse)
async def get_event_qr(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EventQRResponse:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    share_url = f"/e/{event.slug}"
    # Use standard QR code generator service or CDN asset
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={share_url}"
    encoded_text = f"Upload your photos to {event.name or 'our gallery'} at {share_url}"
    whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_text}"

    return EventQRResponse(
        qr_url=qr_url,
        share_url=share_url,
        whatsapp_url=whatsapp_url,
    )


@router.post("/{event_id}/authenticate", response_model=EventPinAuthResponse)
async def authenticate_guest(
    event_id: uuid.UUID,
    payload: EventPinAuthRequest,
    db: AsyncSession = Depends(get_db),
) -> EventPinAuthResponse:
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # If event has no PIN configured or PIN matches
    if not event.guest_pin or event.guest_pin.strip() == payload.pin.strip():
        return EventPinAuthResponse(success=True, message="Authenticated successfully")

    return EventPinAuthResponse(success=False, message="Invalid PIN. Please try again.")


@router.get("/{id_or_slug}/gallery", response_model=GalleryResponse)
async def get_gallery(
    id_or_slug: str,
    album_id: str | None = Query(None),
    cursor: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> GalleryResponse:
    # Resolve Event
    event: Event | None = None
    try:
        event_uuid = uuid.UUID(id_or_slug)
        result = await db.execute(select(Event).where(Event.id == event_uuid))
        event = result.scalar_one_or_none()
    except ValueError:
        pass

    if not event:
        result = await db.execute(select(Event).where(Event.slug == id_or_slug))
        event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # Base query for visible media
    media_query = (
        select(Media)
        .where(Media.event_id == event.id, Media.status == "visible")
        .order_by(Media.created_at.desc())
    )

    if cursor:
        try:
            cursor_uuid = uuid.UUID(cursor)
            cursor_res = await db.execute(
                select(Media.created_at).where(Media.id == cursor_uuid)
            )
            cursor_time = cursor_res.scalar_one_or_none()
            if cursor_time:
                media_query = media_query.where(Media.created_at < cursor_time)
        except ValueError:
            pass

    media_query = media_query.limit(limit + 1)
    res = await db.execute(media_query)
    media_items = list(res.scalars().all())

    next_cursor = None
    if len(media_items) > limit:
        next_cursor = str(media_items[limit - 1].id)
        media_items = media_items[:limit]

    # Fetch albums
    albums_res = await db.execute(
        select(Album).where(Album.event_id == event.id).order_by(Album.created_at.desc())
    )
    albums = list(albums_res.scalars().all())

    # Count total media
    total_res = await db.execute(
        select(func.count(Media.id)).where(
            Media.event_id == event.id, Media.status == "visible"
        )
    )
    total_count = total_res.scalar() or 0

    media_responses = [
        MediaResponse(
            id=m.id,
            event_id=m.event_id,
            uploaded_by=m.uploaded_by,
            guest_session_id=m.guest_session_id,
            type=m.type or "photo",
            status=m.status or "ready",
            url=f"https://cdn.yaadein.com/{m.r2_object_key}" if m.r2_object_key else None,
            thumbnail_url=m.thumbnail_url or (f"https://cdn.yaadein.com/{m.r2_object_key}" if m.r2_object_key else None),
            r2_object_key=m.r2_object_key,
            file_size_bytes=m.file_size_bytes or 0,
            mime_type=m.mime_type,
            width=m.width,
            height=m.height,
            duration_seconds=m.duration_seconds,
            album_ids=[],
            created_at=m.created_at,
        )
        for m in media_items
    ]

    album_responses = [
        AlbumResponse(
            id=a.id,
            event_id=a.event_id,
            name=a.name,
            type=a.type,
            emoji="📁",
            media_count=0,
            dynamic_filters=a.dynamic_filters,
            created_at=a.created_at,
        )
        for a in albums
    ]

    return GalleryResponse(
        media=media_responses,
        albums=album_responses,
        total_count=total_count,
        next_cursor=next_cursor,
    )


@router.post("/{id_or_slug}/face-search", response_model=FaceSearchResponse)
async def face_search(
    id_or_slug: str,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> FaceSearchResponse:
    event: Event | None = None
    try:
        event_uuid = uuid.UUID(id_or_slug)
        result = await db.execute(select(Event).where(Event.id == event_uuid))
        event = result.scalar_one_or_none()
    except ValueError:
        pass

    if not event:
        result = await db.execute(select(Event).where(Event.slug == id_or_slug))
        event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    image_bytes = await image.read()
    if not image_bytes:
        return FaceSearchResponse(media_ids=[])

    face_service = FaceEmbeddingService()
    embeddings = face_service.generate_embeddings(image_bytes)
    if not embeddings:
        return FaceSearchResponse(media_ids=[])

    # Search for matching media with pgvector or embeddings
    search_embedding = embeddings[0]
    matched_media_ids: list[uuid.UUID] = []

    try:
        # Cosine distance search with pgvector (<=> operator)
        result = await db.execute(
            select(FaceEmbedding.media_id)
            .where(FaceEmbedding.event_id == event.id)
            .order_by(FaceEmbedding.embedding.cosine_distance(search_embedding))
            .limit(50)
        )
        matched_media_ids = [row[0] for row in result.fetchall()]
    except Exception:
        # Fallback query for visible media
        fallback_res = await db.execute(
            select(Media.id)
            .where(Media.event_id == event.id, Media.status == "visible")
            .limit(20)
        )
        matched_media_ids = [row[0] for row in fallback_res.fetchall()]

    return FaceSearchResponse(media_ids=matched_media_ids)
