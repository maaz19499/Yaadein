import io
import uuid
from unittest.mock import patch
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event
from src.models.media import Media
from src.workers.tasks.media import _async_process_image_upload
from tests.api.test_events import create_test_user, delete_test_user


def generate_dummy_image_bytes() -> bytes:
    img = Image.new("RGB", (800, 600), color="blue")
    output = io.BytesIO()
    img.save(output, format="JPEG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_process_image_upload_task_success(db_session: AsyncSession):
    # 1. Setup host user and event
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

        # 2. Setup Media DB record in pending_verify status
        media_id = uuid.uuid4()
        r2_object_key = f"events/{event_id}/originals/temp-photo.jpg"
        media = Media(
            id=media_id,
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=r2_object_key,
            idempotency_key=f"idem-{media_id.hex}",
            status="pending_verify",
            file_size_bytes=100000,
            mime_type="image/jpeg",
        )
        db_session.add(media)
        await db_session.commit()

        # 3. Generate dummy image bytes for mock download
        dummy_image_bytes = generate_dummy_image_bytes()

        # 4. Mock R2 storage calls and run the processing task
        with patch(
            "src.services.storage.R2StorageService.get_object_body",
            return_value=dummy_image_bytes,
        ) as mock_get:
            with patch(
                "src.services.storage.R2StorageService.upload_bytes"
            ) as mock_upload:
                with patch(
                    "src.services.moderation.ModerationService.is_image_safe",
                    return_value=True,
                ) as mock_mod:
                    # Execute task synchronously
                    await _async_process_image_upload(str(event_id), str(media_id))

                    # Verify R2 helper downloads original image
                    mock_get.assert_called_once_with(r2_object_key)
                    mock_mod.assert_called_once_with(dummy_image_bytes)

                    # Verify R2 helper uploads two WebP formats (thumbnail & preview)
                    assert mock_upload.call_count == 2

                    # Assert thumbnail call arguments
                    first_call_args = mock_upload.call_args_list[0]
                    assert (
                        first_call_args[0][1]
                        == f"events/{event_id}/thumbnails/{media_id}.webp"
                    )
                    assert first_call_args[0][2] == "image/webp"

                    # Assert preview call arguments
                    second_call_args = mock_upload.call_args_list[1]
                    assert (
                        second_call_args[0][1]
                        == f"events/{event_id}/previews/{media_id}.webp"
                    )
                    assert second_call_args[0][2] == "image/webp"

        # 5. Assert the DB row updates
        # Since DB session is async, we execute SELECT again to see the changes
        db_session.expire_all()
        db_res = await db_session.execute(
            select(Media).where(Media.event_id == event_id, Media.id == media_id)
        )
        db_media = db_res.scalar_one()
        assert db_media.status == "visible"
        assert db_media.width == 800
        assert db_media.height == 600
        assert db_media.phash is not None
        assert len(db_media.phash) == 64
        assert db_media.thumbnail_url is not None
        assert f"events/{event_id}/thumbnails/{media_id}.webp" in db_media.thumbnail_url

        # 6. Clean up
        from sqlalchemy import delete

        await db_session.execute(
            delete(Media).where(Media.event_id == event_id, Media.id == media_id)
        )
        event_result = await db_session.execute(
            select(Event).where(Event.id == event_id)
        )
        db_event = event_result.scalar_one()
        await db_session.delete(db_event)
        await db_session.commit()
    finally:
        # Safely clean up database records to prevent integrity constraint failures on host user deletion
        try:
            await db_session.rollback()
            from sqlalchemy import delete

            await db_session.execute(
                delete(Media).where(Media.event_id == event_id, Media.id == media_id)
            )

            stmt_evt = select(Event).where(Event.id == event_id)
            res_evt = await db_session.execute(stmt_evt)
            e_item = res_evt.scalar_one_or_none()
            if e_item:
                await db_session.delete(e_item)
            await db_session.commit()
        except Exception:
            pass
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_process_image_upload_task_rejected(db_session: AsyncSession) -> None:
    # 1. Setup host user and event
    host_id, _ = await create_test_user(db_session, "Host Priya 2", "host")

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

        # 2. Setup Media DB record in pending_verify status
        media_id = uuid.uuid4()
        r2_object_key = f"events/{event_id}/originals/unsafe-photo.jpg"
        media = Media(
            id=media_id,
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=r2_object_key,
            idempotency_key=f"idem-{media_id.hex}",
            status="pending_verify",
            file_size_bytes=100000,
            mime_type="image/jpeg",
        )
        db_session.add(media)
        await db_session.commit()

        # 3. Generate dummy image bytes for mock download
        dummy_image_bytes = generate_dummy_image_bytes()

        # 4. Mock calls and assert rejection logic
        with patch(
            "src.services.storage.R2StorageService.get_object_body",
            return_value=dummy_image_bytes,
        ):
            with patch(
                "src.services.storage.R2StorageService.upload_bytes"
            ) as mock_upload:
                with patch(
                    "src.services.moderation.ModerationService.is_image_safe",
                    return_value=False,
                ):
                    await _async_process_image_upload(str(event_id), str(media_id))

                    # Uploads should not be triggered
                    mock_upload.assert_not_called()

        # 5. Assert database status is rejected
        db_session.expire_all()
        db_res = await db_session.execute(
            select(Media).where(Media.event_id == event_id, Media.id == media_id)
        )
        db_media = db_res.scalar_one()
        assert db_media.status == "rejected"

        # 6. Clean up
        from sqlalchemy import delete

        await db_session.execute(
            delete(Media).where(Media.event_id == event_id, Media.id == media_id)
        )
        await db_session.delete(event)
        await db_session.commit()
    finally:
        try:
            await db_session.rollback()
            from sqlalchemy import delete

            await db_session.execute(
                delete(Media).where(Media.event_id == event_id, Media.id == media_id)
            )

            stmt_evt = select(Event).where(Event.id == event_id)
            res_evt = await db_session.execute(stmt_evt)
            e_item = res_evt.scalar_one_or_none()
            if e_item:
                await db_session.delete(e_item)
            await db_session.commit()
        except Exception:
            pass
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_process_image_upload_task_duplicate(db_session: AsyncSession) -> None:
    # 1. Setup host user and event
    host_id, _ = await create_test_user(db_session, "Host Priya 3", "host")

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

        # 2. Setup two Media records
        media_id_1 = uuid.uuid4()
        media_id_2 = uuid.uuid4()

        media1 = Media(
            id=media_id_1,
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/photo1.jpg",
            idempotency_key=f"idem-{media_id_1.hex}",
            status="pending_verify",
            file_size_bytes=100000,
            mime_type="image/jpeg",
        )
        media2 = Media(
            id=media_id_2,
            event_id=event_id,
            uploaded_by=host_id,
            type="image",
            r2_object_key=f"events/{event_id}/originals/photo2.jpg",
            idempotency_key=f"idem-{media_id_2.hex}",
            status="pending_verify",
            file_size_bytes=100000,
            mime_type="image/jpeg",
        )
        db_session.add_all([media1, media2])
        await db_session.commit()

        # 3. Generate dummy image bytes
        dummy_image_bytes = generate_dummy_image_bytes()

        # 4. Upload the first image (unique and safe)
        with patch(
            "src.services.storage.R2StorageService.get_object_body",
            return_value=dummy_image_bytes,
        ):
            with patch(
                "src.services.storage.R2StorageService.upload_bytes"
            ) as mock_upload:
                with patch(
                    "src.services.moderation.ModerationService.is_image_safe",
                    return_value=True,
                ):
                    await _async_process_image_upload(str(event_id), str(media_id_1))
                    assert mock_upload.call_count == 2

        # Verify first is visible
        db_session.expire_all()
        db_res1 = await db_session.execute(
            select(Media).where(Media.event_id == event_id, Media.id == media_id_1)
        )
        db_media1 = db_res1.scalar_one()
        assert db_media1.status == "visible"
        assert db_media1.phash is not None
        phash_1 = db_media1.phash

        # 5. Upload the second image (same bytes, identical hash, should trigger duplicate status)
        with patch(
            "src.services.storage.R2StorageService.get_object_body",
            return_value=dummy_image_bytes,
        ):
            with patch(
                "src.services.storage.R2StorageService.upload_bytes"
            ) as mock_upload:
                with patch(
                    "src.services.moderation.ModerationService.is_image_safe",
                    return_value=True,
                ):
                    await _async_process_image_upload(str(event_id), str(media_id_2))
                    # Duplicate upload should not invoke any R2 uploads
                    mock_upload.assert_not_called()

        # Verify second is marked as duplicate with same phash
        db_session.expire_all()
        db_res2 = await db_session.execute(
            select(Media).where(Media.event_id == event_id, Media.id == media_id_2)
        )
        db_media2 = db_res2.scalar_one()
        assert db_media2.status == "duplicate"
        assert db_media2.phash == phash_1

        # 6. Clean up
        from sqlalchemy import delete

        await db_session.execute(delete(Media).where(Media.event_id == event_id))
        await db_session.delete(event)
        await db_session.commit()
    finally:
        try:
            await db_session.rollback()
            from sqlalchemy import delete

            await db_session.execute(delete(Media).where(Media.event_id == event_id))

            stmt_evt = select(Event).where(Event.id == event_id)
            res_evt = await db_session.execute(stmt_evt)
            e_item = res_evt.scalar_one_or_none()
            if e_item:
                await db_session.delete(e_item)
            await db_session.commit()
        except Exception:
            pass
        await delete_test_user(db_session, host_id)
