import uuid
from unittest.mock import patch
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event
from src.models.media import Media
from src.models.guest import Guest
from src.models.face import FaceConsent, FaceEmbedding, FaceCluster
from src.workers.tasks.face import (
    _async_generate_face_embeddings,
    cluster_faces_for_event,
)
from tests.api.test_events import create_test_user, delete_test_user


@pytest.mark.asyncio
async def test_generate_face_embeddings_success(db_session: AsyncSession):
    # 1. Setup host user, event (with face search enabled) and guest uploader
    host_id, _ = await create_test_user(db_session, "Host Face", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event = Event(
            host_id=host_id,
            slug=slug,
            is_wedding=True,
            face_search_enabled=True,
            plan="basic",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        event_id = event.id

        # Setup Guest and active consent
        guest_session_id = uuid.uuid4()
        guest = Guest(
            event_id=event_id,
            guest_session_id=guest_session_id,
            name="Aarav Sharma",
        )
        db_session.add(guest)
        await db_session.flush()

        consent = FaceConsent(
            event_id=event_id,
            guest_session_id=guest_session_id,
            guest_name="Aarav Sharma",
            consent_given_at=event.created_at,
        )
        db_session.add(consent)
        await db_session.flush()
        consent_id = consent.id

        # Setup visible Media
        media_id = uuid.uuid4()
        media = Media(
            id=media_id,
            event_id=event_id,
            guest_session_id=guest_session_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/temp.jpg",
            idempotency_key=f"idem-{media_id.hex}",
            status="visible",
        )
        db_session.add(media)
        await db_session.commit()

        # 2. Mock storage download
        dummy_bytes = b"fake-image-bytes"

        with patch(
            "src.services.storage.R2StorageService.get_object_body",
            return_value=dummy_bytes,
        ) as mock_get:
            # Run the embedding generator
            await _async_generate_face_embeddings(
                str(event_id), str(media_id), str(consent_id)
            )
            mock_get.assert_called_once_with(
                f"events/{event_id}/previews/{media_id}.webp"
            )

        # 3. Assert DB record created
        db_session.expire_all()
        embeddings_res = await db_session.execute(
            select(FaceEmbedding).where(
                FaceEmbedding.event_id == event_id, FaceEmbedding.media_id == media_id
            )
        )
        embeddings = embeddings_res.scalars().all()
        assert len(embeddings) > 0
        for emb in embeddings:
            assert emb.uploader_consent_id == consent_id
            assert emb.embedding is not None
            assert len(emb.embedding) == 512

        # Clean up
        from sqlalchemy import delete

        await db_session.execute(
            delete(FaceEmbedding).where(FaceEmbedding.event_id == event_id)
        )
        await db_session.execute(delete(Media).where(Media.event_id == event_id))
        await db_session.execute(
            delete(FaceConsent).where(FaceConsent.event_id == event_id)
        )
        await db_session.execute(delete(Guest).where(Guest.event_id == event_id))
        await db_session.delete(event)
        await db_session.commit()

    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_face_clustering_job(db_session: AsyncSession):
    # 1. Setup event, guest and consent
    host_id, _ = await create_test_user(db_session, "Host Face 2", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event = Event(
            host_id=host_id,
            slug=slug,
            is_wedding=True,
            face_search_enabled=True,
            plan="basic",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        event_id = event.id

        guest_session_id = uuid.uuid4()
        guest = Guest(
            event_id=event_id,
            guest_session_id=guest_session_id,
            name="Riya Kapoor",
        )
        db_session.add(guest)
        await db_session.flush()

        consent = FaceConsent(
            event_id=event_id,
            guest_session_id=guest_session_id,
            guest_name="Riya Kapoor",
            consent_given_at=event.created_at,
        )
        db_session.add(consent)
        await db_session.flush()

        # Create two media items
        media_id_1 = uuid.uuid4()
        media_id_2 = uuid.uuid4()

        media1 = Media(
            id=media_id_1,
            event_id=event_id,
            guest_session_id=guest_session_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/m1.jpg",
            idempotency_key="idem-m1",
            status="visible",
            thumbnail_url="http://r2/m1-thumb.webp",
        )
        media2 = Media(
            id=media_id_2,
            event_id=event_id,
            guest_session_id=guest_session_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/m2.jpg",
            idempotency_key="idem-m2",
            status="visible",
            thumbnail_url="http://r2/m2-thumb.webp",
        )
        db_session.add_all([media1, media2])
        await db_session.commit()

        # 2. Seed face embeddings with specific vectors
        # Let's seed 3 face embeddings:
        # Vector 1 and Vector 2 are very close (cosine similarity ~ 0.95, distance ~ 0.05 <= 0.4)
        # Vector 3 is far away from them (cosine similarity with Vector 1 ~ 0.2, distance ~ 0.8 > 0.4)
        # Therefore, DBSCAN (with eps=0.4) should group Vector 1 & 2 into one cluster, and Vector 3 into a second cluster.

        vec1 = [0.0] * 512
        vec1[0] = 1.0  # [1, 0, 0, ...]

        vec2 = [0.0] * 512
        vec2[0] = 0.95
        vec2[1] = (1.0 - 0.95**2) ** 0.5  # Unit length vector close to vec1

        vec3 = [0.0] * 512
        vec3[511] = 1.0  # [0, 0, ..., 1] (orthogonal to vec1/vec2)

        emb1 = FaceEmbedding(
            event_id=event_id,
            media_id=media_id_1,
            embedding=vec1,
            uploader_consent_id=consent.id,
            purge_at=event.created_at,
        )
        emb2 = FaceEmbedding(
            event_id=event_id,
            media_id=media_id_1,
            embedding=vec2,
            uploader_consent_id=consent.id,
            purge_at=event.created_at,
        )
        emb3 = FaceEmbedding(
            event_id=event_id,
            media_id=media_id_2,
            embedding=vec3,
            uploader_consent_id=consent.id,
            purge_at=event.created_at,
        )
        db_session.add_all([emb1, emb2, emb3])
        await db_session.commit()

        # 3. Execute clustering
        await cluster_faces_for_event(event_id)

        # 4. Verify results
        db_session.expire_all()

        # Verify face_clusters table populated
        clusters_res = await db_session.execute(
            select(FaceCluster).where(FaceCluster.event_id == event_id)
        )
        clusters = clusters_res.scalars().all()
        assert (
            len(clusters) == 2
        )  # DBSCAN with min_samples=1 groups [emb1, emb2] -> cluster 0, [emb3] -> cluster 1

        # Check embeddings cluster mapping
        embs_res = await db_session.execute(
            select(FaceEmbedding)
            .where(FaceEmbedding.event_id == event_id)
            .order_by(FaceEmbedding.created_at)
        )
        db_embs = embs_res.scalars().all()
        # Find which cluster ID corresponds to which embedding
        # emb1 and emb2 should have the same cluster_id
        assert db_embs[0].cluster_id is not None
        assert db_embs[1].cluster_id is not None
        assert db_embs[0].cluster_id == db_embs[1].cluster_id

        # emb3 should have a different cluster_id
        assert db_embs[2].cluster_id is not None
        assert db_embs[2].cluster_id != db_embs[0].cluster_id

        # Clean up
        from sqlalchemy import delete

        await db_session.execute(
            delete(FaceEmbedding).where(FaceEmbedding.event_id == event_id)
        )
        await db_session.execute(
            delete(FaceCluster).where(FaceCluster.event_id == event_id)
        )
        await db_session.execute(delete(Media).where(Media.event_id == event_id))
        await db_session.execute(
            delete(FaceConsent).where(FaceConsent.event_id == event_id)
        )
        await db_session.execute(delete(Guest).where(Guest.event_id == event_id))
        await db_session.delete(event)
        await db_session.commit()

    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_face_clustering_periodic_job_filters(db_session: AsyncSession):
    from src.workers.tasks.face import _async_cluster_faces_job
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete

    host_id, _ = await create_test_user(db_session, "Host Face Filter", "host")

    try:
        now = datetime.now(timezone.utc)

        # 1. Expired Event (should be clustered)
        event_expired = Event(
            host_id=host_id,
            slug=f"expired-{uuid.uuid4().hex[:8]}",
            face_search_enabled=True,
            face_clustered=False,
            upload_expires_at=now - timedelta(days=1),
            plan="basic",
        )

        # 2. Active Event (should NOT be clustered)
        event_active = Event(
            host_id=host_id,
            slug=f"active-{uuid.uuid4().hex[:8]}",
            face_search_enabled=True,
            face_clustered=False,
            upload_expires_at=now + timedelta(days=1),
            plan="basic",
        )

        db_session.add_all([event_expired, event_active])
        await db_session.commit()
        await db_session.refresh(event_expired)
        await db_session.refresh(event_active)

        # Create guest, consent, media for expired event
        guest_exp = Guest(event_id=event_expired.id, guest_session_id=uuid.uuid4(), name="Guest Exp")
        db_session.add(guest_exp)
        await db_session.flush()

        consent_exp = FaceConsent(
            event_id=event_expired.id,
            guest_session_id=guest_exp.guest_session_id,
            guest_name=guest_exp.name,
            consent_given_at=event_expired.created_at,
        )
        db_session.add(consent_exp)
        await db_session.flush()

        media_exp = Media(
            id=uuid.uuid4(),
            event_id=event_expired.id,
            guest_session_id=guest_exp.guest_session_id,
            type="image",
            r2_object_key=f"events/{event_expired.id}/originals/exp.jpg",
            idempotency_key="idem-exp",
            status="visible",
            thumbnail_url="http://r2/exp-thumb.webp",
        )
        db_session.add(media_exp)
        await db_session.flush()

        # Create guest, consent, media for active event
        guest_act = Guest(event_id=event_active.id, guest_session_id=uuid.uuid4(), name="Guest Act")
        db_session.add(guest_act)
        await db_session.flush()

        consent_act = FaceConsent(
            event_id=event_active.id,
            guest_session_id=guest_act.guest_session_id,
            guest_name=guest_act.name,
            consent_given_at=event_active.created_at,
        )
        db_session.add(consent_act)
        await db_session.flush()

        media_act = Media(
            id=uuid.uuid4(),
            event_id=event_active.id,
            guest_session_id=guest_act.guest_session_id,
            type="image",
            r2_object_key=f"events/{event_active.id}/originals/act.jpg",
            idempotency_key="idem-act",
            status="visible",
            thumbnail_url="http://r2/act-thumb.webp",
        )
        db_session.add(media_act)
        await db_session.flush()

        # Seed embedding for expired event
        emb_expired = FaceEmbedding(
            event_id=event_expired.id,
            media_id=media_exp.id,
            embedding=[0.5] * 512,
            uploader_consent_id=consent_exp.id,
            purge_at=event_expired.created_at,
        )

        # Seed embedding for active event
        emb_active = FaceEmbedding(
            event_id=event_active.id,
            media_id=media_act.id,
            embedding=[0.5] * 512,
            uploader_consent_id=consent_act.id,
            purge_at=event_active.created_at,
        )

        db_session.add_all([emb_expired, emb_active])
        await db_session.commit()

        # Run periodic job
        await _async_cluster_faces_job()

        # Refresh database state
        db_session.expire_all()
        await db_session.refresh(event_expired)
        await db_session.refresh(event_active)

        # Assertions
        assert event_expired.face_clustered is True
        assert event_active.face_clustered is False

        # Verify cluster created for expired event only
        clusters_expired = (await db_session.execute(
            select(FaceCluster).where(FaceCluster.event_id == event_expired.id)
        )).scalars().all()
        assert len(clusters_expired) == 1

        clusters_active = (await db_session.execute(
            select(FaceCluster).where(FaceCluster.event_id == event_active.id)
        )).scalars().all()
        assert len(clusters_active) == 0

        # Clean up
        await db_session.execute(delete(FaceEmbedding).where(FaceEmbedding.event_id.in_([event_expired.id, event_active.id])))
        await db_session.execute(delete(FaceCluster).where(FaceCluster.event_id.in_([event_expired.id, event_active.id])))
        await db_session.execute(delete(Media).where(Media.event_id.in_([event_expired.id, event_active.id])))
        await db_session.execute(delete(FaceConsent).where(FaceConsent.event_id.in_([event_expired.id, event_active.id])))
        await db_session.execute(delete(Guest).where(Guest.event_id.in_([event_expired.id, event_active.id])))
        await db_session.delete(event_expired)
        await db_session.delete(event_active)
        await db_session.commit()

    finally:
        await delete_test_user(db_session, host_id)

