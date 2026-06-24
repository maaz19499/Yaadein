import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_upload_identity, UploadIdentity
from src.models.event import Event
from src.models.user import User
from src.models.album import Album, AlbumMedia
from src.models.media import Media
from src.models.face import FaceEmbedding
from src.schemas.album import AlbumCreate, AlbumResponse
from src.schemas.media import MediaResponse

router = APIRouter(tags=["albums"])


@router.post("/{event_id}/albums", response_model=AlbumResponse, status_code=status.HTTP_201_CREATED)
async def create_album(
    event_id: uuid.UUID,
    album_in: AlbumCreate,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> Album:
    # 1. Verify event exists
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # 2. Authorize
    if identity.user_id:
        user_res = await db.execute(select(User).where(User.id == identity.user_id))
        user = user_res.scalar_one()
        if event.host_id != identity.user_id and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to manage albums for this event.",
            )
    elif identity.guest_session_id:
        if identity.event_id != event_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to manage albums for this event.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized identity.",
        )

    # 3. Handle Static vs Dynamic album creation
    new_album = Album(
        event_id=event_id,
        name=album_in.name,
        type=album_in.type,
        dynamic_filters=album_in.dynamic_filters if album_in.type == "dynamic" else None,
    )
    db.add(new_album)
    await db.flush()

    if album_in.type == "static" and album_in.media_ids:
        # Verify media belongs to this event and is visible before associating
        media_res = await db.execute(
            select(Media.id).where(
                Media.event_id == event_id,
                Media.id.in_(album_in.media_ids),
                Media.status == "visible",
            )
        )
        valid_media_ids = [row[0] for row in media_res.fetchall()]
        
        for media_id in valid_media_ids:
            junction = AlbumMedia(
                event_id=event_id,
                album_id=new_album.id,
                media_id=media_id,
            )
            db.add(junction)

    await db.commit()
    await db.refresh(new_album)
    return new_album


@router.get("/{event_id}/albums", response_model=list[AlbumResponse])
async def list_albums(
    event_id: uuid.UUID,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> list[Album]:
    # 1. Verify event exists
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # 2. Authorize
    if identity.guest_session_id and identity.event_id != event_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view albums for this event.",
        )

    albums_res = await db.execute(
        select(Album).where(Album.event_id == event_id).order_by(Album.created_at.desc())
    )
    return list(albums_res.scalars().all())


@router.get("/{event_id}/albums/{album_id}", response_model=list[MediaResponse])
async def get_album_media(
    event_id: uuid.UUID,
    album_id: uuid.UUID,
    identity: UploadIdentity = Depends(get_upload_identity),
    db: AsyncSession = Depends(get_db),
) -> list[Media]:
    # 1. Verify event exists
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # 2. Authorize
    if identity.guest_session_id and identity.event_id != event_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view albums for this event.",
        )

    # 3. Fetch Album
    album_res = await db.execute(
        select(Album).where(Album.event_id == event_id, Album.id == album_id)
    )
    album = album_res.scalar_one_or_none()
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found.",
        )

    # 4. Fetch media items matching the album type
    if album.type == "dynamic":
        # Extract cluster IDs from dynamic filters
        dynamic_filters = album.dynamic_filters or {}
        face_cluster_ids = dynamic_filters.get("face_cluster_ids", [])
        
        # Parse to UUIDs
        try:
            face_cluster_uuids = [
                uuid.UUID(cid) if isinstance(cid, str) else cid
                for cid in face_cluster_ids
            ]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid face cluster UUID formats in dynamic filters.",
            )

        if not face_cluster_uuids:
            return []

        # Find all media items matching the face clusters for this event
        media_stmt = (
            select(Media)
            .where(
                Media.event_id == event_id,
                Media.status == "visible",
                Media.id.in_(
                    select(FaceEmbedding.media_id)
                    .where(
                        FaceEmbedding.event_id == event_id,
                        FaceEmbedding.cluster_id.in_(face_cluster_uuids),
                    )
                )
            )
            .order_by(Media.created_at.desc())
        )
        res = await db.execute(media_stmt)
        return list(res.scalars().all())

    else:
        # Static album: Fetch via junction table join
        media_stmt = (
            select(Media)
            .join(
                AlbumMedia,
                (AlbumMedia.event_id == Media.event_id)
                & (AlbumMedia.media_id == Media.id),
            )
            .where(
                AlbumMedia.event_id == event_id,
                AlbumMedia.album_id == album_id,
                Media.status == "visible",
            )
            .order_by(Media.created_at.desc())
        )
        res = await db.execute(media_stmt)
        return list(res.scalars().all())
