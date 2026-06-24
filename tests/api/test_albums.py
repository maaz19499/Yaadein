import uuid
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event
from src.models.media import Media
from src.models.guest import Guest
from src.models.face import FaceConsent, FaceEmbedding, FaceCluster
from src.models.album import Album, AlbumMedia
from tests.api.test_events import create_test_user, delete_test_user


@pytest.mark.asyncio
async def test_albums_lifecycle(client: TestClient, db_session: AsyncSession):
    # 1. Setup host user, event, and guest
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event_res = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True, "face_search_enabled": True},
            headers=headers,
        )
        assert event_res.status_code == status.HTTP_201_CREATED
        event_id = uuid.UUID(event_res.json()["id"])

        # Setup registered guest session
        guest_session_id = uuid.uuid4()
        guest_res = client.post(
            f"/api/v1/events/{event_id}/guests",
            json={
                "guest_session_id": str(guest_session_id),
                "name": "Karan Johar",
                "phone": "+919876543210",
                "face_search_consent": True,
            },
        )
        assert guest_res.status_code == status.HTTP_200_OK

        # Guest headers for accessing albums API
        guest_headers = {
            "X-Guest-Session-ID": str(guest_session_id),
            "X-Event-ID": str(event_id),
        }

        # Create two visible media items for the event
        media_id_1 = uuid.uuid4()
        media_id_2 = uuid.uuid4()

        media1 = Media(
            id=media_id_1,
            event_id=event_id,
            guest_session_id=guest_session_id,
            type="image",
            r2_object_key="events/m1.jpg",
            idempotency_key="idem-m1",
            status="visible",
            thumbnail_url="http://r2/m1.webp",
        )
        media2 = Media(
            id=media_id_2,
            event_id=event_id,
            guest_session_id=guest_session_id,
            type="image",
            r2_object_key="events/m2.jpg",
            idempotency_key="idem-m2",
            status="visible",
            thumbnail_url="http://r2/m2.webp",
        )
        db_session.add_all([media1, media2])
        await db_session.commit()

        # 2. POST /events/{event_id}/albums: Create static album as Host
        static_album_res = client.post(
            f"/api/v1/events/{event_id}/albums",
            json={
                "name": "Family Portraits",
                "type": "static",
                "media_ids": [str(media_id_1)],
            },
            headers=headers,
        )
        assert static_album_res.status_code == status.HTTP_201_CREATED
        static_data = static_album_res.json()
        assert static_data["name"] == "Family Portraits"
        assert static_data["type"] == "static"
        static_album_id = uuid.UUID(static_data["id"])

        # 3. POST /events/{event_id}/albums: Create dynamic album as Host
        cluster_id = uuid.uuid4()
        dynamic_album_res = client.post(
            f"/api/v1/events/{event_id}/albums",
            json={
                "name": "Groom's Friends",
                "type": "dynamic",
                "dynamic_filters": {
                    "face_cluster_ids": [str(cluster_id)]
                },
            },
            headers=headers,
        )
        assert dynamic_album_res.status_code == status.HTTP_201_CREATED
        dynamic_data = dynamic_album_res.json()
        assert dynamic_data["name"] == "Groom's Friends"
        assert dynamic_data["type"] == "dynamic"
        assert dynamic_data["dynamic_filters"]["face_cluster_ids"] == [str(cluster_id)]
        dynamic_album_id = uuid.UUID(dynamic_data["id"])

        # 4. GET /events/{event_id}/albums: List albums as Guest
        list_res = client.get(f"/api/v1/events/{event_id}/albums", headers=guest_headers)
        assert list_res.status_code == status.HTTP_200_OK
        list_data = list_res.json()
        assert len(list_data) == 2

        # 5. GET /events/{event_id}/albums/{album_id}: Fetch media items matching static album
        static_media_res = client.get(
            f"/api/v1/events/{event_id}/albums/{static_album_id}",
            headers=guest_headers,
        )
        assert static_media_res.status_code == status.HTTP_200_OK
        static_media_data = static_media_res.json()
        assert len(static_media_data) == 1
        assert static_media_data[0]["id"] == str(media_id_1)

        # 6. GET /events/{event_id}/albums/{album_id}: Fetch media items matching dynamic album
        # Seed an embedding mapping to the face cluster for media2
        consent_stmt = select(FaceConsent).where(
            FaceConsent.event_id == event_id,
            FaceConsent.guest_session_id == guest_session_id
        )
        consent_res = await db_session.execute(consent_stmt)
        consent_obj = consent_res.scalar_one()

        # Seed face cluster and mapping embedding
        cluster_obj = FaceCluster(
            id=cluster_id,
            event_id=event_id,
        )
        emb_obj = FaceEmbedding(
            event_id=event_id,
            media_id=media_id_2,
            embedding=[0.1] * 512,
            cluster_id=cluster_id,
            uploader_consent_id=consent_obj.id,
            purge_at=event_res.json()["storage_expires_at"],
        )
        db_session.add_all([cluster_obj, emb_obj])
        await db_session.commit()

        dynamic_media_res = client.get(
            f"/api/v1/events/{event_id}/albums/{dynamic_album_id}",
            headers=guest_headers,
        )
        assert dynamic_media_res.status_code == status.HTTP_200_OK
        dynamic_media_data = dynamic_media_res.json()
        assert len(dynamic_media_data) == 1
        assert dynamic_media_data[0]["id"] == str(media_id_2)

        # 7. Authorization Error: check guest session mismatch rejects access
        wrong_guest_headers = {
            "X-Guest-Session-ID": str(uuid.uuid4()),
            "X-Event-ID": str(event_id),
        }
        err_res = client.get(
            f"/api/v1/events/{event_id}/albums",
            headers=wrong_guest_headers,
        )
        # Should return HTTP 403 Forbidden because guest is unregistered
        assert err_res.status_code == status.HTTP_403_FORBIDDEN

        # Clean up event
        from sqlalchemy import delete
        await db_session.execute(delete(FaceEmbedding).where(FaceEmbedding.event_id == event_id))
        await db_session.execute(delete(FaceCluster).where(FaceCluster.event_id == event_id))
        await db_session.execute(delete(AlbumMedia).where(AlbumMedia.event_id == event_id))
        await db_session.execute(delete(Album).where(Album.event_id == event_id))
        await db_session.execute(delete(Media).where(Media.event_id == event_id))

        event_stmt = select(Event).where(Event.id == event_id)
        db_event = (await db_session.execute(event_stmt)).scalar_one()
        await db_session.delete(db_event)
        await db_session.commit()

    finally:
        await delete_test_user(db_session, host_id)
