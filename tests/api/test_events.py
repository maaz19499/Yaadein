from datetime import datetime, timedelta, timezone
import uuid
import jwt
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.user import AuthUser
from src.models.event import Event


async def create_test_user(db: AsyncSession, name: str, role: str) -> tuple[uuid.UUID, dict[str, str]]:
    user_id = uuid.uuid4()
    phone = f"+91{uuid.uuid4().int % 10000000000:010d}"
    
    auth_user = AuthUser(
        id=user_id,
        phone=phone,
        raw_user_meta_data={"name": name, "role": role}
    )
    db.add(auth_user)
    await db.commit()

    payload = {
        "sub": str(user_id),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "role": "authenticated",
    }
    token = jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
    return user_id, {"Authorization": f"Bearer {token}"}


async def delete_test_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(select(AuthUser).where(AuthUser.id == user_id))
    auth_user = result.scalar_one_or_none()
    if auth_user:
        await db.delete(auth_user)
        await db.commit()


@pytest.mark.asyncio
async def test_create_event_success(client: TestClient, db_session: AsyncSession):
    # Setup host user
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True, "face_search_enabled": False},
            headers=headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["slug"] == slug
        assert data["plan"] == "basic"
        assert data["is_wedding"] is True
        assert data["face_search_enabled"] is False
        assert data["host_id"] == str(host_id)
        assert "storage_expires_at" in data

        # Check database
        event_id = uuid.UUID(data["id"])
        result = await db_session.execute(select(Event).where(Event.id == event_id))
        db_event = result.scalar_one_or_none()
        assert db_event is not None
        assert db_event.slug == slug

        # Cleanup event
        await db_session.delete(db_event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_create_event_invalid_role(client: TestClient, db_session: AsyncSession):
    # User with regular guest role (not host/photographer/admin)
    guest_id, headers = await create_test_user(db_session, "Regular Guest", "guest")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True},
            headers=headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Only hosts" in response.json()["detail"]
    finally:
        await delete_test_user(db_session, guest_id)


@pytest.mark.asyncio
async def test_create_event_unauthenticated(client: TestClient):
    slug = f"wedding-{uuid.uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/events",
        json={"slug": slug, "is_wedding": True},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_create_event_duplicate_slug(client: TestClient, db_session: AsyncSession):
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")
    slug = f"wedding-{uuid.uuid4().hex[:8]}"

    try:
        # Create first
        response1 = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True},
            headers=headers,
        )
        assert response1.status_code == status.HTTP_201_CREATED
        event1_id = uuid.UUID(response1.json()["id"])

        # Create second with same slug
        response2 = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": False},
            headers=headers,
        )
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
        assert "slug already exists" in response2.json()["detail"]

        # Cleanup
        result = await db_session.execute(select(Event).where(Event.id == event1_id))
        event1 = result.scalar_one()
        await db_session.delete(event1)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_list_events(client: TestClient, db_session: AsyncSession):
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug1 = f"slug1-{uuid.uuid4().hex[:8]}"
        slug2 = f"slug2-{uuid.uuid4().hex[:8]}"
        
        response1 = client.post(
            "/api/v1/events",
            json={"slug": slug1, "is_wedding": True},
            headers=headers,
        )
        response2 = client.post(
            "/api/v1/events",
            json={"slug": slug2, "is_wedding": False},
            headers=headers,
        )
        
        event1_id = uuid.UUID(response1.json()["id"])
        event2_id = uuid.UUID(response2.json()["id"])

        # List
        response = client.get("/api/v1/events", headers=headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 2
        
        slugs = [e["slug"] for e in data]
        assert slug1 in slugs
        assert slug2 in slugs

        # Cleanup
        for eid in (event1_id, event2_id):
            result = await db_session.execute(select(Event).where(Event.id == eid))
            event = result.scalar_one()
            await db_session.delete(event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_get_event_by_slug(client: TestClient, db_session: AsyncSession):
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")
    slug = f"wedding-{uuid.uuid4().hex[:8]}"

    try:
        response = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True, "face_search_enabled": True},
            headers=headers,
        )
        event_id = uuid.UUID(response.json()["id"])

        # Fetch publicly
        get_response = client.get(f"/api/v1/events/slug/{slug}")
        assert get_response.status_code == status.HTTP_200_OK
        data = get_response.json()
        assert data["slug"] == slug
        assert data["face_search_enabled"] is True
        assert data["is_wedding"] is True
        assert "storage_expires_at" not in data  # Public endpoint has minimal data

        # Non-existent
        not_found = client.get("/api/v1/events/slug/non-existent-slug-xyz")
        assert not_found.status_code == status.HTTP_404_NOT_FOUND

        # Cleanup
        result = await db_session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one()
        await db_session.delete(event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_update_event(client: TestClient, db_session: AsyncSession):
    host1_id, headers1 = await create_test_user(db_session, "Host Priya", "host")
    host2_id, headers2 = await create_test_user(db_session, "Host Rohan", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        response = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True, "face_search_enabled": False},
            headers=headers1,
        )
        event_id = uuid.UUID(response.json()["id"])

        # Update success (Host 1 owns it)
        new_slug = f"new-slug-{uuid.uuid4().hex[:8]}"
        update_response = client.put(
            f"/api/v1/events/{event_id}",
            json={"slug": new_slug, "is_wedding": False, "face_search_enabled": True},
            headers=headers1,
        )
        assert update_response.status_code == status.HTTP_200_OK
        updated_data = update_response.json()
        assert updated_data["slug"] == new_slug
        assert updated_data["is_wedding"] is False
        assert updated_data["face_search_enabled"] is True

        # Update forbidden (Host 2 does not own it)
        forbidden_response = client.put(
            f"/api/v1/events/{event_id}",
            json={"is_wedding": True},
            headers=headers2,
        )
        assert forbidden_response.status_code == status.HTTP_403_FORBIDDEN
        assert "Not authorized" in forbidden_response.json()["detail"]

        # Cleanup
        result = await db_session.execute(select(Event).where(Event.id == event_id))
        event = result.scalar_one()
        await db_session.delete(event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host1_id)
        await delete_test_user(db_session, host2_id)
