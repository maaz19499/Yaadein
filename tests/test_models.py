from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User, AuthUser
from src.models.event import Event, GalleryCache, QRCode
from src.models.guest import Guest
from src.models.media import Media, Export
from src.models.face import FaceConsent, FaceCluster, FaceEmbedding
from src.models.album import Album, AlbumMedia
from src.models.payment import Payment


async def test_supabase_auth_sync_trigger(db_session: AsyncSession):
    # 1. Insert a mock user directly into the auth.users table using AuthUser model
    user_id = uuid.uuid4()
    phone = f"+91{uuid.uuid4().int % 10000000000:010d}"
    user_name = "Auth Sync Test Guest"
    user_role = "photographer"
    
    auth_user = AuthUser(
        id=user_id,
        phone=phone,
        raw_user_meta_data={"name": user_name, "role": user_role}
    )
    db_session.add(auth_user)
    await db_session.commit()

    # 2. Check if trigger synced to public.users profile
    result = await db_session.execute(select(User).where(User.id == user_id))
    synced_user = result.scalar_one_or_none()

    assert synced_user is not None
    assert synced_user.id == user_id
    assert synced_user.phone == phone
    assert synced_user.name == user_name
    assert synced_user.role == user_role

    # Cleanup
    await db_session.delete(auth_user)
    await db_session.commit()


async def test_full_domain_models_creation(db_session: AsyncSession):
    # 1. Create Host User (in auth.users, synced to users)
    host_id = uuid.uuid4()
    host_phone = f"+91{uuid.uuid4().int % 10000000000:010d}"
    host_user = AuthUser(
        id=host_id,
        phone=host_phone,
        raw_user_meta_data={"name": "Host Priya", "role": "host"}
    )
    db_session.add(host_user)
    await db_session.commit()

    # 2. Create Event
    event_slug = f"wedding-{uuid.uuid4().hex[:8]}"
    event = Event(
        host_id=host_id,
        slug=event_slug,
        face_search_enabled=True,
        plan="premium",
        is_wedding=True
    )
    db_session.add(event)
    await db_session.commit()
    assert event.id is not None

    # 3. Create Guest
    guest_session_id = uuid.uuid4()
    guest = Guest(
        event_id=event.id,
        guest_session_id=guest_session_id,
        name="Guest Rahul",
        phone="+919999999999"
    )
    db_session.add(guest)
    await db_session.commit()
    assert guest.id is not None

    # 4. Create Media (Partitioned)
    media_id = uuid.uuid4()
    media = Media(
        id=media_id,
        event_id=event.id,
        guest_session_id=guest_session_id,
        type="image",
        r2_object_key=f"events/{event.id}/originals/{media_id}.jpg",
        idempotency_key=f"idem-{media_id}",
        status="pending_verify",
        phash="1" * 64,  # 64-bit binary string
        width=1920,
        height=1080
    )
    db_session.add(media)
    await db_session.commit()

    # 5. Create Face Consent & Face Cluster & Face Embedding
    consent = FaceConsent(
        event_id=event.id,
        guest_session_id=guest_session_id,
        guest_name="Guest Rahul",
        consent_given_at=datetime.now(timezone.utc)
    )
    db_session.add(consent)
    await db_session.flush()

    cluster = FaceCluster(
        event_id=event.id,
        matched_guest_session_id=guest_session_id,
        matched_guest_name="Guest Rahul"
    )
    db_session.add(cluster)
    await db_session.flush()

    # embedding is pgvector 512 float dimensions
    embedding = FaceEmbedding(
        event_id=event.id,
        media_id=media_id,
        embedding=[0.1] * 512,
        cluster_id=cluster.id,
        uploader_consent_id=consent.id,
        purge_at=datetime.now(timezone.utc)
    )
    db_session.add(embedding)
    await db_session.commit()

    # 6. Create Album (Partitioned)
    album = Album(
        event_id=event.id,
        name="Rahul's Album",
        type="static"
    )
    db_session.add(album)
    await db_session.commit()
    assert album.id is not None

    # Create AlbumMedia Junction (Partitioned)
    album_media = AlbumMedia(
        event_id=event.id,
        album_id=album.id,
        media_id=media.id
    )
    db_session.add(album_media)
    await db_session.commit()

    # 7. Verify all records exist and query them
    media_res = await db_session.execute(
        select(Media).where(Media.event_id == event.id, Media.id == media_id)
    )
    assert media_res.scalar_one_or_none() is not None

    emb_res = await db_session.execute(
        select(FaceEmbedding).where(FaceEmbedding.event_id == event.id, FaceEmbedding.media_id == media_id)
    )
    embedding_row = emb_res.scalar_one_or_none()
    assert embedding_row is not None
    assert len(embedding_row.embedding) == 512

    # Query duplicate perceptual hashes (Hamming distance scan)
    # bit_count(phash # :incoming_phash) <= 10
    # In postgres, we check bitwise XOR
    phash_val = "1" * 64
    dup_res = await db_session.execute(
        text(
            "SELECT id FROM media WHERE event_id = :event_id AND bit_count(phash # CAST(:incoming_phash AS bit(64))) <= 10"
        ),
        {"event_id": event.id, "incoming_phash": phash_val}
    )
    dup_row = dup_res.all()
    assert len(dup_row) == 1
    assert dup_row[0][0] == media_id

    # 8. Clean up everything (cascade deletes)
    await db_session.delete(event)
    await db_session.delete(host_user)
    await db_session.commit()
