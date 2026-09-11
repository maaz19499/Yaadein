import uuid
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.event import Event
from src.models.payment import Payment
from tests.api.test_events import create_test_user, delete_test_user


@pytest.mark.asyncio
async def test_payment_status_update_flow(
    client: TestClient, db_session: AsyncSession
):
    # 1. Setup host user and second unauthorized user
    host_id, host_headers = await create_test_user(db_session, "Host Vikram", "host")
    other_id, other_headers = await create_test_user(db_session, "Other User", "host")

    try:
        # 2. Create paid event (plan = "basic"), should have pending status and pending payment
        slug = f"wedding-{uuid.uuid4().hex[:8]}"
        event_res = client.post(
            "/api/v1/events",
            json={
                "name": "Vikram Wedding",
                "slug": slug,
                "plan": "basic",
                "is_wedding": True,
            },
            headers=host_headers,
        )
        assert event_res.status_code == status.HTTP_201_CREATED
        event_data = event_res.json()
        event_id = uuid.UUID(event_data["id"])
        assert event_data["status"] == "pending"

        # 3. Verify payment was automatically created with pending status
        payment_get_res = client.get(
            f"/api/v1/payments/events/{event_id}",
            headers=host_headers,
        )
        assert payment_get_res.status_code == status.HTTP_200_OK
        payment_data = payment_get_res.json()
        assert payment_data["status"] == "pending"
        assert payment_data["plan"] == "basic"
        payment_id = uuid.UUID(payment_data["id"])

        # 4. Unauthorized user cannot update payment status
        forbidden_res = client.post(
            f"/api/v1/payments/events/{event_id}/status",
            json={"status": "success"},
            headers=other_headers,
        )
        assert forbidden_res.status_code == status.HTTP_403_FORBIDDEN

        # 5. Host updates payment status to 'success'
        order_id = f"order_{uuid.uuid4().hex[:8]}"
        razorpay_payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        update_res = client.post(
            f"/api/v1/payments/events/{event_id}/status",
            json={
                "status": "success",
                "order_id": order_id,
                "razorpay_payment_id": razorpay_payment_id,
            },
            headers=host_headers,
        )
        assert update_res.status_code == status.HTTP_200_OK
        updated_data = update_res.json()
        assert updated_data["status"] == "success"
        assert updated_data["order_id"] == order_id
        assert updated_data["razorpay_payment_id"] == razorpay_payment_id
        assert updated_data["event_status"] == "active"

        # 6. Verify in database that both Payment and Event have updated status
        db_session.expire_all()
        event_db = (
            await db_session.execute(select(Event).where(Event.id == event_id))
        ).scalar_one()
        assert event_db.status == "active"

        payment_db = (
            await db_session.execute(select(Payment).where(Payment.id == payment_id))
        ).scalar_one()
        assert payment_db.status == "success"
        assert payment_db.order_id == order_id

        # 7. Test PATCH /api/v1/payments/{payment_id}/status
        patch_res = client.patch(
            f"/api/v1/payments/{payment_id}/status",
            json={"status": "refunded"},
            headers=host_headers,
        )
        assert patch_res.status_code == status.HTTP_200_OK
        assert patch_res.json()["status"] == "refunded"

    finally:
        # Cleanup
        await db_session.execute(
            select(Payment).where(Payment.user_id.in_([host_id, other_id]))
        )
        await delete_test_user(db_session, host_id)
        await delete_test_user(db_session, other_id)
