import asyncio
import io
import uuid
from PIL import Image
from sqlalchemy import select, update

from src.config import settings
from src.database import async_session_maker
from src.models.media import Media, Export
from src.services.images import resize_image_width, generate_phash
from src.services.moderation import ModerationService
from src.services.storage import R2StorageService
from src.workers.app import celery_app


async def _async_process_image_upload(event_id_str: str, media_id_str: str) -> None:
    event_id = uuid.UUID(event_id_str)
    media_id = uuid.UUID(media_id_str)

    # 1. Fetch Media record to get r2_object_key and guest_session_id
    async with async_session_maker() as session:
        result = await session.execute(
            select(Media).where(Media.event_id == event_id, Media.id == media_id)
        )
        media = result.scalar_one_or_none()
        if not media:
            raise ValueError(
                f"Media record not found for event_id={event_id}, id={media_id}"
            )
        r2_object_key = media.r2_object_key
        guest_session_id = media.guest_session_id

    # 2. Download original image from R2
    storage_service = R2StorageService()
    response = storage_service.get_object_body(r2_object_key)

    # 3. Generate perceptual hash (pHash)
    phash_str = generate_phash(response)

    # 4. Moderation Scan
    moderation_service = ModerationService()
    is_safe = moderation_service.is_image_safe(response)
    if not is_safe:
        async with async_session_maker() as session:
            await session.execute(
                update(Media)
                .where(Media.event_id == event_id, Media.id == media_id)
                .values(status="rejected")
            )
            await session.commit()
        return

    # 5. Duplicate Detection
    async with async_session_maker() as session:
        duplicates = await Media.find_duplicates(session, event_id, phash_str)
        if duplicates:
            await session.execute(
                update(Media)
                .where(Media.event_id == event_id, Media.id == media_id)
                .values(status="duplicate", phash=phash_str)
            )
            await session.commit()
            return

    # 6. Load image to get original dimensions
    img = Image.open(io.BytesIO(response))
    orig_width, orig_height = img.size

    # 7. Generate thumbnail (400px width) and preview (1600px width) WebP
    thumbnail_bytes = resize_image_width(response, 400)
    preview_bytes = resize_image_width(response, 1600)

    # 8. Upload thumbnail and preview to R2
    thumbnail_key = f"events/{event_id}/thumbnails/{media_id}.webp"
    preview_key = f"events/{event_id}/previews/{media_id}.webp"

    # We use a standard upload wrapper on storage service
    storage_service.upload_bytes(thumbnail_bytes, thumbnail_key, "image/webp")
    storage_service.upload_bytes(preview_bytes, preview_key, "image/webp")

    # Construct the thumbnail URL
    thumbnail_url = (
        f"{settings.R2_ENDPOINT_URL}/{settings.R2_BUCKET_NAME}/{thumbnail_key}"
    )

    # 9. Update Media record in DB
    async with async_session_maker() as session:
        await session.execute(
            update(Media)
            .where(Media.event_id == event_id, Media.id == media_id)
            .values(
                thumbnail_url=thumbnail_url,
                width=orig_width,
                height=orig_height,
                phash=phash_str,
                status="visible",
            )
        )
        await session.commit()

    # 10. Trigger face embedding generation if uploader is a consenting guest and event has face search enabled
    if guest_session_id:
        from src.models.event import Event
        from src.models.face import FaceConsent

        async with async_session_maker() as session:
            evt_res = await session.execute(select(Event).where(Event.id == event_id))
            event = evt_res.scalar_one_or_none()

            if event and event.face_search_enabled:
                consent_res = await session.execute(
                    select(FaceConsent).where(
                        FaceConsent.event_id == event_id,
                        FaceConsent.guest_session_id == guest_session_id,
                        FaceConsent.consent_revoked_at.is_(None),
                    )
                )
                consent = consent_res.scalar_one_or_none()
                if consent:
                    from src.workers.tasks.face import generate_face_embeddings

                    generate_face_embeddings.delay(
                        str(event_id), str(media_id), str(consent.id)
                    )


@celery_app.task(name="src.workers.tasks.media.process_image_upload")
def process_image_upload(event_id: str, media_id: str) -> None:
    """
    Celery task that downscales the uploaded image to thumbnail and preview size,
    uploads them to R2, and marks the image as visible in the database.
    """
    asyncio.run(_async_process_image_upload(event_id, media_id))


async def _async_generate_zip_export(
    export_id_str: str, event_id_str: str, scope: str, album_id_str: str | None = None
) -> None:
    export_id = uuid.UUID(export_id_str)
    event_id = uuid.UUID(event_id_str)
    album_id = uuid.UUID(album_id_str) if album_id_str else None

    # 1. Update export status to 'processing'
    async with async_session_maker() as session:
        await session.execute(
            update(Export).where(Export.id == export_id).values(status="processing")
        )
        await session.commit()

    try:
        # 2. Fetch all visible media matching scope
        async with async_session_maker() as session:
            if scope == "full_event":
                media_stmt = select(Media).where(
                    Media.event_id == event_id, Media.status == "visible"
                )
                media_res = await session.execute(media_stmt)
                media_items = list(media_res.scalars().all())
            elif scope == "album" and album_id:
                from src.models.album import Album
                from src.models.face import FaceEmbedding
                from src.models.album import AlbumMedia

                album_res = await session.execute(
                    select(Album).where(
                        Album.event_id == event_id, Album.id == album_id
                    )
                )
                album = album_res.scalar_one_or_none()
                if not album:
                    raise ValueError(f"Album {album_id} not found.")

                if album.type == "dynamic":
                    dynamic_filters = album.dynamic_filters or {}
                    face_cluster_ids = dynamic_filters.get("face_cluster_ids", [])
                    face_cluster_uuids = [
                        uuid.UUID(cid) if isinstance(cid, str) else cid
                        for cid in face_cluster_ids
                    ]
                    if not face_cluster_uuids:
                        media_items = []
                    else:
                        media_stmt = select(Media).where(
                            Media.event_id == event_id,
                            Media.status == "visible",
                            Media.id.in_(
                                select(FaceEmbedding.media_id).where(
                                    FaceEmbedding.event_id == event_id,
                                    FaceEmbedding.cluster_id.in_(face_cluster_uuids),
                                )
                            ),
                        )
                        media_res = await session.execute(media_stmt)
                        media_items = list(media_res.scalars().all())
                else:
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
                    )
                    media_res = await session.execute(media_stmt)
                    media_items = list(media_res.scalars().all())
            else:
                media_items = []

        if not media_items:
            # If no media items are found, mark as failed
            async with async_session_maker() as session:
                await session.execute(
                    update(Export).where(Export.id == export_id).values(status="failed")
                )
                await session.commit()
            return

        # 3. Create zip file on worker disk
        import tempfile
        import zipfile
        import os

        storage_service = R2StorageService()

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            tmp_zip_path = tmp_file.name

        try:
            with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for m in media_items:
                    try:
                        file_bytes = storage_service.get_object_body(m.r2_object_key)
                        _, ext = os.path.splitext(m.r2_object_key)
                        # Name file inside zip with media ID to ensure unique filenames
                        filename_in_zip = f"{m.id}{ext}"
                        zip_file.writestr(filename_in_zip, file_bytes)
                    except Exception:
                        # Log error and skip this media file
                        pass

            # 4. Upload zip file to R2 private exports path
            export_key = f"events/{event_id}/exports/{export_id}.zip"
            with open(tmp_zip_path, "rb") as f:
                zip_data = f.read()
            storage_service.upload_bytes(zip_data, export_key, "application/zip")
        finally:
            # Clean up temporary file from worker disk
            if os.path.exists(tmp_zip_path):
                os.remove(tmp_zip_path)

        # 5. Generate temporary presigned download URL for the ZIP file (valid for 24 hours)
        download_url = storage_service.generate_presigned_download_url(
            export_key, expires_in=86400
        )

        # 6. Update export status to 'ready'
        async with async_session_maker() as session:
            await session.execute(
                update(Export)
                .where(Export.id == export_id)
                .values(status="ready", download_url=download_url)
            )
            await session.commit()

    except Exception as e:
        async with async_session_maker() as session:
            await session.execute(
                update(Export).where(Export.id == export_id).values(status="failed")
            )
            await session.commit()
        raise e


@celery_app.task(name="src.workers.tasks.media.generate_zip_export")
def generate_zip_export(
    export_id: str, event_id: str, scope: str, album_id: str | None = None
) -> None:
    """
    Celery task that downloads original media assets for an event or album,
    compresses them into a ZIP archive, and uploads it back to private R2 storage.
    """
    asyncio.run(_async_generate_zip_export(export_id, event_id, scope, album_id))
