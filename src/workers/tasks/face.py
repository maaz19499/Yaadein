import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from typing import cast

from src.database import async_session_maker
from src.models.event import Event
from src.models.media import Media
from src.models.face import FaceConsent, FaceEmbedding, FaceCluster
from src.services.storage import R2StorageService
from src.services.face import FaceEmbeddingService
from src.workers.app import celery_app


async def _async_generate_face_embeddings(
    event_id_str: str,
    media_id_str: str,
    consent_id_str: str,
) -> None:
    event_id = uuid.UUID(event_id_str)
    media_id = uuid.UUID(media_id_str)
    consent_id = uuid.UUID(consent_id_str)

    async with async_session_maker() as session:
        # 1. Fetch Media record to confirm existence and visibility
        media_result = await session.execute(
            select(Media).where(Media.event_id == event_id, Media.id == media_id)
        )
        media = media_result.scalar_one_or_none()
        if not media or media.status != "visible":
            return  # Skip processing if media doesn't exist or is not visible

        # 2. Fetch Event and ensure face search is enabled
        event_result = await session.execute(select(Event).where(Event.id == event_id))
        event = event_result.scalar_one_or_none()
        if not event or not event.face_search_enabled:
            return  # Skip processing if event has face search disabled

        # 3. Verify that consent has not been revoked
        consent_result = await session.execute(
            select(FaceConsent).where(
                FaceConsent.id == consent_id,
                FaceConsent.consent_revoked_at.is_(None),
            )
        )
        consent = consent_result.scalar_one_or_none()
        if not consent:
            return  # Skip processing if consent is revoked

        # 4. Download Preview WebP from R2 (with fallback to original key)
        storage_service = R2StorageService()
        preview_key = f"events/{event_id}/previews/{media_id}.webp"
        try:
            image_bytes = storage_service.get_object_body(preview_key)
        except Exception:
            # Fallback to original image object key
            try:
                image_bytes = storage_service.get_object_body(media.r2_object_key)
            except Exception:
                raise ValueError(
                    f"Could not download file from key {preview_key} or {media.r2_object_key}"
                )

        # 5. Extract face embeddings
        face_service = FaceEmbeddingService()
        embeddings = face_service.generate_embeddings(image_bytes)

        # 6. Save face embedding records to DB
        purge_at = event.storage_expires_at or (
            datetime.now(timezone.utc) + timedelta(days=30)
        )

        for emb in embeddings:
            db_embedding = FaceEmbedding(
                event_id=event_id,
                media_id=media_id,
                embedding=emb,
                uploader_consent_id=consent_id,
                purge_at=purge_at,
            )
            session.add(db_embedding)

        await session.commit()


@celery_app.task(name="src.workers.tasks.face.generate_face_embeddings")
def generate_face_embeddings(event_id: str, media_id: str, consent_id: str) -> None:
    """
    Celery task that extracts and registers face embeddings from an uploaded media item
    under the uploader's consent.
    """
    asyncio.run(_async_generate_face_embeddings(event_id, media_id, consent_id))


async def cluster_faces_for_event(event_id: uuid.UUID) -> None:
    """
    Groups face embeddings for a single event using cosine distance DBSCAN clustering.
    Creates face clusters and maps embeddings to their corresponding cluster.
    """
    async with async_session_maker() as session:
        # Fetch all face embeddings for the event
        embeddings_res = await session.execute(
            select(FaceEmbedding).where(FaceEmbedding.event_id == event_id)
        )
        embeddings = list(embeddings_res.scalars().all())
        if not embeddings:
            return

        # Cluster embeddings using FaceEmbeddingService
        face_service = FaceEmbeddingService()
        # Filter out None embeddings to be type-safe
        valid_embeddings = [emb for emb in embeddings if emb.embedding is not None]
        emb_vectors = [cast(list[float], emb.embedding) for emb in valid_embeddings]
        labels = face_service.cluster_embeddings(emb_vectors, eps=0.4, min_samples=1)

        # Group embeddings by DBSCAN cluster label
        groups: dict[int, list[FaceEmbedding]] = {}
        for emb, label in zip(valid_embeddings, labels):
            if label != -1:
                groups.setdefault(label, []).append(emb)

        # Process each cluster group
        for label, group_embs in groups.items():
            # Find if any embeddings in this cluster group already have an assigned cluster ID
            existing_cluster_ids = {
                e.cluster_id for e in group_embs if e.cluster_id is not None
            }

            cluster_id = None
            if existing_cluster_ids:
                # Reuse the first existing cluster ID to preserve references/guest assignments
                cluster_id = list(existing_cluster_ids)[0]
            else:
                # Generate new FaceCluster
                new_cluster = FaceCluster(event_id=event_id)
                session.add(new_cluster)
                await session.flush()
                cluster_id = new_cluster.id

            # Map embeddings to this cluster ID
            for e in group_embs:
                e.cluster_id = cluster_id

            # Assign cluster cover thumbnail URL based on the first media thumbnail in the cluster
            if group_embs:
                first_emb = group_embs[0]
                media_res = await session.execute(
                    select(Media).where(
                        Media.event_id == event_id, Media.id == first_emb.media_id
                    )
                )
                media = media_res.scalar_one_or_none()
                if media and media.thumbnail_url:
                    # Update cluster cover thumbnail url
                    cluster_res = await session.execute(
                        select(FaceCluster).where(FaceCluster.id == cluster_id)
                    )
                    cluster = cluster_res.scalar_one_or_none()
                    if cluster:
                        cluster.cover_thumbnail_url = media.thumbnail_url

        # Explicitly clear cluster IDs for noise / outliers (label -1)
        for emb, label in zip(embeddings, labels):
            if label == -1:
                emb.cluster_id = None

        await session.commit()


async def _async_cluster_faces_job() -> None:
    now = datetime.now(timezone.utc)
    # Fetch all events whose upload period has expired and have not been clustered yet
    async with async_session_maker() as session:
        events_res = await session.execute(
            select(Event).where(
                Event.face_search_enabled == True,
                Event.face_clustered == False,
                (Event.upload_expires_at.is_(None)) | (Event.upload_expires_at <= now),
            )
        )
        events = list(events_res.scalars().all())
        event_ids = [e.id for e in events]

    for event_id in event_ids:
        try:
            await cluster_faces_for_event(event_id)
            async with async_session_maker() as session:
                await session.execute(
                    update(Event)
                    .where(Event.id == event_id)
                    .values(face_clustered=True)
                )
                await session.commit()
        except Exception:
            # Prevent failures in one event from breaking the entire daily clustering job
            pass


@celery_app.task(name="src.workers.tasks.face.cluster_faces_job")
def cluster_faces_job() -> None:
    """
    Daily batch job to run DBSCAN clustering on face embeddings across active events.
    """
    asyncio.run(_async_cluster_faces_job())
