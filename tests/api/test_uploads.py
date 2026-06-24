import uuid
from unittest.mock import patch, MagicMock
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event
from src.models.media import Media
from tests.api.test_events import create_test_user, delete_test_user


@pytest.mark.asyncio
async def test_presign_urls_host_success(client: TestClient, db_session: AsyncSession):
    # 1. Setup host user and event
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event_res = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True},
            headers=headers,
        )
        assert event_res.status_code == status.HTTP_201_CREATED
        event_id = uuid.UUID(event_res.json()["id"])

        # 2. Call uploads/presign endpoint
        payload = {
            "event_id": str(event_id),
            "files": [
                {
                    "client_file_id": "temp-file-under-10",
                    "file_name": "selfie.jpg",
                    "file_size_bytes": 4 * 1024 * 1024,  # 4MB
                    "mime_type": "image/jpeg",
                    "checksum": "sha256-12345",
                },
                {
                    "client_file_id": "temp-file-over-10",
                    "file_name": "dance_video.mp4",
                    "file_size_bytes": 25
                    * 1024
                    * 1024,  # 25MB -> 3 parts (10MB, 10MB, 5MB)
                    "mime_type": "video/mp4",
                    "checksum": "sha256-67890",
                },
            ],
        }

        # Mock R2 Storage multipart init to return a mock upload id
        with patch("src.services.storage.boto3.client") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.return_value = mock_s3
            mock_s3.create_multipart_upload.return_value = {
                "UploadId": "mock-upload-id-123"
            }
            mock_s3.generate_presigned_url.return_value = (
                "https://mock-r2-url.com/presigned"
            )
            mock_s3.create_bucket.return_value = {}

            response = client.post(
                "/api/v1/uploads/presign",
                json=payload,
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "files" in data
        assert len(data["files"]) == 2

        # Assert selfie details
        selfie = next(
            f for f in data["files"] if f["client_file_id"] == "temp-file-under-10"
        )
        assert selfie["r2_upload_id"] is None
        assert selfie["chunk_size_bytes"] is None
        assert len(selfie["chunks"]) == 1
        assert selfie["chunks"][0]["part_number"] == 1
        assert "events/" in selfie["r2_object_key"]
        assert selfie["idempotency_key"] is not None

        # Assert video details
        video = next(
            f for f in data["files"] if f["client_file_id"] == "temp-file-over-10"
        )
        assert video["r2_upload_id"] == "mock-upload-id-123"
        assert video["chunk_size_bytes"] == 10 * 1024 * 1024
        assert len(video["chunks"]) == 3
        assert [c["part_number"] for c in video["chunks"]] == [1, 2, 3]

        # 3. Clean up event
        event_result = await db_session.execute(
            select(Event).where(Event.id == event_id)
        )
        db_event = event_result.scalar_one()
        await db_session.delete(db_event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_presign_urls_guest_success(client: TestClient, db_session: AsyncSession):
    # 1. Setup host user and event
    host_id, host_headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event_res = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True},
            headers=host_headers,
        )
        event_id = uuid.UUID(event_res.json()["id"])

        # 2. Register guest session
        guest_session_id = uuid.uuid4()
        client.post(
            f"/api/v1/events/{event_id}/guests",
            json={
                "guest_session_id": str(guest_session_id),
                "name": "Rahul Mehta",
                "phone": "+919123456780",
                "face_search_consent": True,
            },
        )

        # 3. Call uploads/presign endpoint with guest headers
        guest_headers = {
            "X-Guest-Session-ID": str(guest_session_id),
            "X-Event-ID": str(event_id),
        }
        payload = {
            "event_id": str(event_id),
            "files": [
                {
                    "client_file_id": "temp-file-guest",
                    "file_name": "selfie.jpg",
                    "file_size_bytes": 1 * 1024 * 1024,
                    "mime_type": "image/jpeg",
                }
            ],
        }

        with patch("src.services.storage.boto3.client") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.return_value = mock_s3
            mock_s3.generate_presigned_url.return_value = (
                "https://mock-r2-url.com/presigned"
            )
            mock_s3.create_bucket.return_value = {}

            response = client.post(
                "/api/v1/uploads/presign",
                json=payload,
                headers=guest_headers,
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["client_file_id"] == "temp-file-guest"

        # 4. Clean up event
        event_result = await db_session.execute(
            select(Event).where(Event.id == event_id)
        )
        db_event = event_result.scalar_one()
        await db_session.delete(db_event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_media_confirm_success_and_idempotency(
    client: TestClient, db_session: AsyncSession
):
    # 1. Setup host user and event
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event_res = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True},
            headers=headers,
        )
        event_id = uuid.UUID(event_res.json()["id"])

        # 2. Confirm Single Part File
        idempotency_key = f"idem-{uuid.uuid4().hex}"
        r2_object_key = f"events/{event_id}/originals/temp-selfie.jpg"

        confirm_payload = {
            "event_id": str(event_id),
            "idempotency_key": idempotency_key,
            "r2_object_key": r2_object_key,
            "r2_upload_id": None,
        }

        # Mock R2 head_object returning metadata
        mock_head = {
            "ContentLength": 500000,
            "ContentType": "image/jpeg",
            "ETag": '"etag-checksum-value"',
        }

        with patch(
            "src.services.storage.R2StorageService.head_object", return_value=mock_head
        ):
            with patch(
                "src.workers.tasks.media.process_image_upload.delay"
            ) as mock_celery:
                response = client.post(
                    "/api/v1/media/confirm",
                    json=confirm_payload,
                    headers=headers,
                )
                assert response.status_code == status.HTTP_202_ACCEPTED
                data = response.json()
                assert data["status"] == "pending_verify"
                assert "queued" in data["message"]

                # Assert database entry was created
                db_res = await db_session.execute(
                    select(Media).where(
                        Media.event_id == event_id,
                        Media.idempotency_key == idempotency_key,
                    )
                )
                db_media = db_res.scalar_one_or_none()
                assert db_media is not None
                assert db_media.status == "pending_verify"
                assert db_media.file_size_bytes == 500000
                assert db_media.mime_type == "image/jpeg"
                assert db_media.checksum == "etag-checksum-value"

                # Assert celery task dispatched
                mock_celery.assert_called_once_with(str(event_id), str(db_media.id))

                # 3. Test IDEMPOTENCY: Call again with the exact same request body
                # Should return the existing record's status and NOT trigger Celery again
                mock_celery.reset_mock()
                response_idem = client.post(
                    "/api/v1/media/confirm",
                    json=confirm_payload,
                    headers=headers,
                )
                assert response_idem.status_code == status.HTTP_202_ACCEPTED
                data_idem = response_idem.json()
                assert data_idem["status"] == "pending_verify"
                assert "idempotency match" in data_idem["message"]
                mock_celery.assert_not_called()

        # 4. Clean up event and media
        # We need to manually delete media first because of composite key constraints
        db_res = await db_session.execute(
            select(Media).where(
                Media.event_id == event_id, Media.idempotency_key == idempotency_key
            )
        )
        db_media = db_res.scalar_one()
        await db_session.delete(db_media)

        event_result = await db_session.execute(
            select(Event).where(Event.id == event_id)
        )
        db_event = event_result.scalar_one()
        await db_session.delete(db_event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)
