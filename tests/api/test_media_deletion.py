import uuid
from unittest.mock import patch, MagicMock
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from src.main import app
from src.api.deps import get_db, get_upload_identity, UploadIdentity
from src.models.media import Media
from src.models.user import User
from src.models.event import Event
from src.services.storage import R2StorageService


class MockResult:
    def __init__(self, value):
        self._val = value

    def scalar_one_or_none(self):
        return self._val


class MockDB:
    def __init__(self, media=None, event=None, user=None):
        self.media = media
        self.event = event
        self.user = user
        self.deleted_items = []
        self.executed_statements = []
        self.committed = False

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        # Determine query type based on statement string
        s_str = str(stmt)
        if "FROM media" in s_str:
            return MockResult(self.media)
        elif "FROM events" in s_str:
            return MockResult(self.event)
        elif "FROM users" in s_str:
            return MockResult(self.user)
        return MockResult(None)

    async def delete(self, obj):
        self.deleted_items.append(obj)

    async def commit(self):
        self.committed = True


@pytest.fixture
def client():
    return TestClient(app)


def test_host_deletes_media_success(client: TestClient):
    host_id = uuid.uuid4()
    event_id = uuid.uuid4()
    media_id = uuid.uuid4()
    r2_key = f"events/{event_id}/originals/photo.jpg"

    mock_event = Event(id=event_id, host_id=host_id)
    mock_media = Media(
        id=media_id,
        event_id=event_id,
        uploaded_by=host_id,
        r2_object_key=r2_key,
        thumbnail_url=f"https://r2.storage/events/{event_id}/thumbnails/{media_id}.webp",
    )
    mock_user = User(id=host_id, role="host")
    mock_db = MockDB(media=mock_media, event=mock_event, user=mock_user)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_upload_identity] = lambda: UploadIdentity(user_id=host_id)

    try:
        with patch("src.api.v1.media.R2StorageService") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage_cls.return_value = mock_storage

            res = client.delete(f"/api/v1/media/{media_id}")
            assert res.status_code == status.HTTP_204_NO_CONTENT

            # Verify R2 keys purged
            expected_keys = [
                r2_key,
                f"events/{event_id}/previews/{media_id}.webp",
                f"events/{event_id}/thumbnails/{media_id}.webp",
            ]
            mock_storage.delete_objects.assert_called_once_with(expected_keys)

            # Verify DB operations
            assert mock_media in mock_db.deleted_items
            assert mock_db.committed is True
    finally:
        app.dependency_overrides.clear()


def test_guest_uploader_right_to_erasure_success(client: TestClient):
    guest_session_id = uuid.uuid4()
    event_id = uuid.uuid4()
    media_id = uuid.uuid4()
    r2_key = f"events/{event_id}/originals/guest_photo.jpg"

    mock_event = Event(id=event_id, host_id=uuid.uuid4())
    mock_media = Media(
        id=media_id,
        event_id=event_id,
        guest_session_id=guest_session_id,
        r2_object_key=r2_key,
    )
    mock_db = MockDB(media=mock_media, event=mock_event)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_upload_identity] = lambda: UploadIdentity(
        event_id=event_id, guest_session_id=guest_session_id
    )

    try:
        with patch("src.api.v1.media.R2StorageService") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage_cls.return_value = mock_storage

            res = client.delete(f"/api/v1/media/{media_id}")
            assert res.status_code == status.HTTP_204_NO_CONTENT

            mock_storage.delete_objects.assert_called_once()
            assert mock_media in mock_db.deleted_items
            assert mock_db.committed is True
    finally:
        app.dependency_overrides.clear()


def test_registered_uploader_deletes_media_success(client: TestClient):
    uploader_id = uuid.uuid4()
    host_id = uuid.uuid4()
    event_id = uuid.uuid4()
    media_id = uuid.uuid4()

    mock_event = Event(id=event_id, host_id=host_id)
    mock_media = Media(
        id=media_id,
        event_id=event_id,
        uploaded_by=uploader_id,
        r2_object_key=f"events/{event_id}/originals/pic.jpg",
    )
    mock_user = User(id=uploader_id, role="guest")
    mock_db = MockDB(media=mock_media, event=mock_event, user=mock_user)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_upload_identity] = lambda: UploadIdentity(user_id=uploader_id)

    try:
        with patch("src.api.v1.media.R2StorageService") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage_cls.return_value = mock_storage

            res = client.delete(f"/api/v1/media/{media_id}")
            assert res.status_code == status.HTTP_204_NO_CONTENT
            assert mock_media in mock_db.deleted_items
    finally:
        app.dependency_overrides.clear()


def test_admin_deletes_media_success(client: TestClient):
    admin_id = uuid.uuid4()
    host_id = uuid.uuid4()
    event_id = uuid.uuid4()
    media_id = uuid.uuid4()

    mock_event = Event(id=event_id, host_id=host_id)
    mock_media = Media(
        id=media_id,
        event_id=event_id,
        uploaded_by=uuid.uuid4(),
        r2_object_key=f"events/{event_id}/originals/admin_purge.jpg",
    )
    mock_user = User(id=admin_id, role="admin")
    mock_db = MockDB(media=mock_media, event=mock_event, user=mock_user)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_upload_identity] = lambda: UploadIdentity(user_id=admin_id)

    try:
        with patch("src.api.v1.media.R2StorageService") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage_cls.return_value = mock_storage

            res = client.delete(f"/api/v1/media/{media_id}")
            assert res.status_code == status.HTTP_204_NO_CONTENT
            assert mock_media in mock_db.deleted_items
    finally:
        app.dependency_overrides.clear()


def test_unauthorized_guest_cannot_delete_other_media(client: TestClient):
    media_guest_id = uuid.uuid4()
    other_guest_id = uuid.uuid4()
    event_id = uuid.uuid4()
    media_id = uuid.uuid4()

    mock_event = Event(id=event_id, host_id=uuid.uuid4())
    mock_media = Media(
        id=media_id,
        event_id=event_id,
        guest_session_id=media_guest_id,
        r2_object_key=f"events/{event_id}/originals/secret.jpg",
    )
    mock_db = MockDB(media=mock_media, event=mock_event)

    app.dependency_overrides[get_db] = lambda: mock_db
    # Caller is a different guest
    app.dependency_overrides[get_upload_identity] = lambda: UploadIdentity(
        event_id=event_id, guest_session_id=other_guest_id
    )

    try:
        with patch("src.api.v1.media.R2StorageService") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage_cls.return_value = mock_storage

            res = client.delete(f"/api/v1/media/{media_id}")
            assert res.status_code == status.HTTP_403_FORBIDDEN
            assert "Not authorized" in res.json()["detail"]
            mock_storage.delete_objects.assert_not_called()
            assert len(mock_db.deleted_items) == 0
    finally:
        app.dependency_overrides.clear()


def test_unauthorized_user_cannot_delete_media(client: TestClient):
    user_id = uuid.uuid4()
    host_id = uuid.uuid4()
    event_id = uuid.uuid4()
    media_id = uuid.uuid4()

    mock_event = Event(id=event_id, host_id=host_id)
    mock_media = Media(
        id=media_id,
        event_id=event_id,
        uploaded_by=uuid.uuid4(),  # Someone else
        r2_object_key=f"events/{event_id}/originals/pic.jpg",
    )
    mock_user = User(id=user_id, role="user")  # Regular user, not host, not admin
    mock_db = MockDB(media=mock_media, event=mock_event, user=mock_user)

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_upload_identity] = lambda: UploadIdentity(user_id=user_id)

    try:
        with patch("src.api.v1.media.R2StorageService") as mock_storage_cls:
            mock_storage = MagicMock()
            mock_storage_cls.return_value = mock_storage

            res = client.delete(f"/api/v1/media/{media_id}")
            assert res.status_code == status.HTTP_403_FORBIDDEN
            mock_storage.delete_objects.assert_not_called()
            assert len(mock_db.deleted_items) == 0
    finally:
        app.dependency_overrides.clear()


def test_delete_nonexistent_media_returns_404(client: TestClient):
    mock_db = MockDB(media=None)
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_upload_identity] = lambda: UploadIdentity(user_id=uuid.uuid4())

    try:
        res = client.delete(f"/api/v1/media/{uuid.uuid4()}")
        assert res.status_code == status.HTTP_404_NOT_FOUND
    finally:
        app.dependency_overrides.clear()


def test_storage_service_delete_methods():
    with patch("src.services.storage.boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3

        service = R2StorageService()

        # Test single delete
        service.delete_object("events/123/photo.jpg")
        mock_s3.delete_object.assert_called_with(
            Bucket=service.bucket_name, Key="events/123/photo.jpg"
        )

        # Test empty delete
        service.delete_object("")

        # Test batch delete
        keys = ["k1", "k2", "k3"]
        service.delete_objects(keys)
        mock_s3.delete_objects.assert_called_with(
            Bucket=service.bucket_name,
            Delete={"Objects": [{"Key": "k1"}, {"Key": "k2"}, {"Key": "k3"}], "Quiet": True},
        )
