from datetime import datetime, timezone
import uuid
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import AuthUser
from src.models.event import Event
from src.models.guest import Guest
from src.models.face import FaceConsent
from tests.api.test_events import create_test_user, delete_test_user


@pytest.mark.asyncio
async def test_register_guest_success(client: TestClient, db_session: AsyncSession):
    # Setup host and event
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event_res = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True},
            headers=headers,
        )
        event_id = uuid.UUID(event_res.json()["id"])

        # Register guest
        session_id = uuid.uuid4()
        response = client.post(
            f"/api/v1/events/{event_id}/guests",
            json={
                "guest_session_id": str(session_id),
                "name": "Rahul Mehta",
                "phone": "+919123456780",
                "face_search_consent": True,
            },
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["guest"]["guest_session_id"] == str(session_id)
        assert data["guest"]["name"] == "Rahul Mehta"
        assert data["guest"]["face_search_consent"] is True

        # Assert DB rows exist
        g_result = await db_session.execute(
            select(Guest).where(Guest.event_id == event_id, Guest.guest_session_id == session_id)
        )
        db_guest = g_result.scalar_one_or_none()
        assert db_guest is not None
        assert db_guest.name == "Rahul Mehta"
        assert db_guest.phone == "+919123456780"

        c_result = await db_session.execute(
            select(FaceConsent).where(FaceConsent.event_id == event_id, FaceConsent.guest_session_id == session_id)
        )
        db_consent = c_result.scalar_one_or_none()
        assert db_consent is not None
        assert db_consent.guest_name == "Rahul Mehta"
        assert db_consent.consent_given_at is not None
        assert db_consent.consent_revoked_at is None

        # Clean up event (cascades to guest and consent)
        event_result = await db_session.execute(select(Event).where(Event.id == event_id))
        db_event = event_result.scalar_one()
        await db_session.delete(db_event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_register_guest_reentry_update(client: TestClient, db_session: AsyncSession):
    host_id, headers = await create_test_user(db_session, "Host Priya", "host")

    try:
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event_res = client.post(
            "/api/v1/events",
            json={"slug": slug, "is_wedding": True},
            headers=headers,
        )
        event_id = uuid.UUID(event_res.json()["id"])
        session_id = uuid.uuid4()

        # 1. Register guest first time
        client.post(
            f"/api/v1/events/{event_id}/guests",
            json={
                "guest_session_id": str(session_id),
                "name": "Rahul Mehta",
                "phone": "+919123456780",
                "face_search_consent": True,
            },
        )

        # 2. Register again with new name/phone
        response = client.post(
            f"/api/v1/events/{event_id}/guests",
            json={
                "guest_session_id": str(session_id),
                "name": "Rahul M. Mehta",
                "phone": "+919999999999",
                "face_search_consent": True,
            },
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["guest"]["name"] == "Rahul M. Mehta"
        assert data["guest"]["face_search_consent"] is True

        # Check DB updates
        g_result = await db_session.execute(
            select(Guest).where(Guest.event_id == event_id, Guest.guest_session_id == session_id)
        )
        db_guest = g_result.scalar_one()
        assert db_guest.name == "Rahul M. Mehta"
        assert db_guest.phone == "+919999999999"

        # 3. Register with consent = False (revoking)
        response_revoke = client.post(
            f"/api/v1/events/{event_id}/guests",
            json={
                "guest_session_id": str(session_id),
                "name": "Rahul M. Mehta",
                "face_search_consent": False,
            },
        )
        assert response_revoke.status_code == status.HTTP_200_OK
        data_revoke = response_revoke.json()
        assert data_revoke["guest"]["face_search_consent"] is False

        # Check DB revocation
        c_result = await db_session.execute(
            select(FaceConsent).where(FaceConsent.event_id == event_id, FaceConsent.guest_session_id == session_id)
        )
        db_consent = c_result.scalar_one()
        assert db_consent.consent_revoked_at is not None

        # Clean up
        event_result = await db_session.execute(select(Event).where(Event.id == event_id))
        db_event = event_result.scalar_one()
        await db_session.delete(db_event)
        await db_session.commit()
    finally:
        await delete_test_user(db_session, host_id)


@pytest.mark.asyncio
async def test_register_guest_nonexistent_event(client: TestClient):
    random_event_id = uuid.uuid4()
    response = client.post(
        f"/api/v1/events/{random_event_id}/guests",
        json={
            "guest_session_id": str(uuid.uuid4()),
            "name": "Rahul Mehta",
            "face_search_consent": True,
        },
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Event not found" in response.json()["detail"]


