import io
import os
import uuid
import zipfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.event import Event
from src.models.media import Media, Export
from src.workers.tasks.media import _async_generate_zip_export
from tests.api.test_events import create_test_user, delete_test_user


@pytest.mark.asyncio
async def test_download_media_success(client: TestClient, db_session: AsyncSession):
    # Setup host and event
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event = Event(
            host_id=host_id,
            slug=slug,
            is_wedding=True,
            face_search_enabled=False,
            plan="basic",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        event_id = event.id

        # Add media item
        media_id = uuid.uuid4()
        media = Media(
            id=media_id,
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/photo1.jpg",
            idempotency_key=f"idem-{media_id.hex}",
            status="visible",
            file_size_bytes=1000,
            mime_type="image/jpeg",
        )
        db_session.add(media)
        await db_session.commit()

        # Call download endpoint with host auth
        mock_presigned_url = "https://mock-r2.com/photo1.jpg?token=mock"
        with patch(
            "src.services.storage.R2StorageService.generate_presigned_download_url",
            return_value=mock_presigned_url,
        ) as mock_gen:
            response = client.get(
                f"/api/v1/media/{event_id}/{media_id}/download",
                headers=headers,
                follow_redirects=False,
            )

            # Assert 307 Redirect
            assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
            assert response.headers["location"] == mock_presigned_url
            mock_gen.assert_called_once_with(media.r2_object_key, expires_in=300)

        # Clean up
        from sqlalchemy import delete
        await db_session.execute(delete(Media).where(Media.event_id == event_id))
        await db_session.delete(event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_download_media_overage_limits(client: TestClient, db_session: AsyncSession):
    # Setup host and event
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event = Event(
            host_id=host_id,
            slug=slug,
            is_wedding=True,
            face_search_enabled=False,
            plan="limited_plan",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        event_id = event.id

        # Insert some prior photos
        media_prior_1 = Media(
            id=uuid.uuid4(),
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/p1.jpg",
            idempotency_key="idem-p1",
            status="visible",
            file_size_bytes=1000,
            created_at=datetime.now(timezone.utc),
        )
        media_prior_2 = Media(
            id=uuid.uuid4(),
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/p2.jpg",
            idempotency_key="idem-p2",
            status="visible",
            file_size_bytes=2000,
            created_at=datetime.now(timezone.utc),
        )
        # Target media is created AFTER prior photos
        target_media = Media(
            id=uuid.uuid4(),
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/target.jpg",
            idempotency_key="idem-target",
            status="visible",
            file_size_bytes=500,
            created_at=datetime.now(timezone.utc),
        )

        db_session.add_all([media_prior_1, media_prior_2, target_media])
        await db_session.commit()

        # 1. Test count limit of 2:
        # Since target_media is the 3rd photo (prior count is 2), it should be blocked when limit is 2.
        test_limits = {
            "limited_plan": {
                "max_count": 2,
                "max_size_bytes": None,
            }
        }
        with patch.dict(settings.PLAN_LIMITS, test_limits):
            response = client.get(
                f"/api/v1/media/{event_id}/{target_media.id}/download",
                headers=headers,
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert response.json()["error"] == "DOWNLOAD_LOCKED"
            assert "limit exceeded" in response.json()["message"]

        # 2. Test size limit of 2500 bytes:
        # Cumulative prior size is 3000 bytes (1000 + 2000), which exceeds 2500 limit.
        test_limits_size = {
            "limited_plan": {
                "max_count": None,
                "max_size_bytes": 2500,
            }
        }
        with patch.dict(settings.PLAN_LIMITS, test_limits_size):
            response = client.get(
                f"/api/v1/media/{event_id}/{target_media.id}/download",
                headers=headers,
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert response.json()["error"] == "DOWNLOAD_LOCKED"
            assert "limit exceeded" in response.json()["message"]

        # Clean up
        from sqlalchemy import delete
        await db_session.execute(delete(Media).where(Media.event_id == event_id))
        await db_session.delete(event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_exports_api_flow(client: TestClient, db_session: AsyncSession):
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event = Event(
            host_id=host_id,
            slug=slug,
            is_wedding=True,
            face_search_enabled=False,
            plan="basic",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        event_id = event.id

        # 1. Trigger export using Celery mock
        with patch("src.workers.tasks.media.generate_zip_export.delay") as mock_delay:
            response = client.post(
                f"/api/v1/events/{event_id}/exports",
                json={"scope": "full_event"},
                headers=headers,
            )
            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            assert "export_id" in data
            assert data["status"] == "queued"
            export_id = uuid.UUID(data["export_id"])

            mock_delay.assert_called_once_with(
                str(export_id), str(event_id), "full_event", None
            )

        # 2. Query export status
        response_status = client.get(
            f"/api/v1/events/{event_id}/exports/{export_id}",
            headers=headers,
        )
        assert response_status.status_code == status.HTTP_200_OK
        assert response_status.json()["status"] == "queued"
        assert response_status.json()["download_url"] is None

        # Clean up
        from sqlalchemy import delete
        await db_session.execute(delete(Export).where(Export.event_id == event_id))
        await db_session.delete(event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_generate_zip_export_task(db_session: AsyncSession):
    # Setup event and media items
    host_id, _ = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event = Event(
            host_id=host_id,
            slug=slug,
            is_wedding=True,
            face_search_enabled=False,
            plan="basic",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        event_id = event.id

        # Add mock visible media items
        media_id_1 = uuid.uuid4()
        media_id_2 = uuid.uuid4()
        m1 = Media(
            id=media_id_1,
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/m1.jpg",
            idempotency_key="idem-m1",
            status="visible",
            file_size_bytes=100,
        )
        m2 = Media(
            id=media_id_2,
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/m2.jpg",
            idempotency_key="idem-m2",
            status="visible",
            file_size_bytes=200,
        )
        db_session.add_all([m1, m2])

        # Create export record
        export_id = uuid.uuid4()
        export_rec = Export(
            id=export_id,
            event_id=event_id,
            requested_by=host_id,
            scope="full_event",
            status="queued",
        )
        db_session.add(export_rec)
        await db_session.commit()

        # Mock download body and upload calls
        dummy_content_1 = b"photo1content"
        dummy_content_2 = b"photo2content"

        def get_object_mock(key: str) -> bytes:
            if "m1.jpg" in key:
                return dummy_content_1
            return dummy_content_2

        # Executing zip task
        with patch(
            "src.services.storage.R2StorageService.get_object_body",
            side_effect=get_object_mock,
        ):
            with patch(
                "src.services.storage.R2StorageService.upload_bytes"
            ) as mock_upload:
                with patch(
                    "src.services.storage.R2StorageService.generate_presigned_download_url",
                    return_value="https://presigned.zip",
                ):
                    await _async_generate_zip_export(
                        str(export_id), str(event_id), "full_event"
                    )

                    # Verify ZIP upload is called
                    assert mock_upload.call_count == 1
                    call_args = mock_upload.call_args
                    assert (
                        call_args[0][1] == f"events/{event_id}/exports/{export_id}.zip"
                    )
                    assert call_args[0][2] == "application/zip"

                    # Verify that contents are a valid zip
                    zip_data = call_args[0][0]
                    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                        namelist = z.namelist()
                        assert f"{media_id_1}.jpg" in namelist
                        assert f"{media_id_2}.jpg" in namelist
                        assert z.read(f"{media_id_1}.jpg") == dummy_content_1
                        assert z.read(f"{media_id_2}.jpg") == dummy_content_2

        # Check export status is updated to ready
        db_session.expire_all()
        result = await db_session.execute(select(Export).where(Export.id == export_id))
        updated_export = result.scalar_one()
        assert updated_export.status == "ready"
        assert updated_export.download_url == "https://presigned.zip"

        # Clean up
        from sqlalchemy import delete
        await db_session.execute(delete(Export).where(Export.event_id == event_id))
        await db_session.execute(delete(Media).where(Media.event_id == event_id))
        await db_session.delete(event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)
