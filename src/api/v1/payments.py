import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db
from src.models.event import Event
from src.models.payment import Payment
from src.models.user import User
from src.schemas.payment import (
    PaymentCreateRequest,
    PaymentResponse,
    PaymentStatusUpdateRequest,
)

router = APIRouter(tags=["payments"])


@router.get("/events/{event_id}", response_model=PaymentResponse)
async def get_event_payment(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """
    Fetches the payment record associated with an event.
    """
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    if event.host_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view payments for this event.",
        )

    payment_res = await db.execute(
        select(Payment)
        .where(Payment.event_id == event_id)
        .order_by(Payment.created_at.desc())
    )
    payment = payment_res.scalars().first()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No payment record found for this event.",
        )

    return PaymentResponse(
        id=payment.id,
        user_id=payment.user_id,
        event_id=payment.event_id,
        plan=payment.plan,
        amount=payment.amount,
        status=payment.status,
        order_id=payment.order_id,
        razorpay_payment_id=payment.razorpay_payment_id,
        created_at=payment.created_at,
        event_status=event.status,
    )


@router.post("/events/{event_id}/status", response_model=PaymentResponse)
async def update_event_payment_status(
    event_id: uuid.UUID,
    payload: PaymentStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """
    Updates the payment status for an event. When marked as 'success',
    automatically activates the event (event.status = 'active').
    """
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    if event.host_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update payments for this event.",
        )

    # Find existing payment or create one if none exists
    payment_res = await db.execute(
        select(Payment)
        .where(Payment.event_id == event_id)
        .order_by(Payment.created_at.desc())
    )
    payment = payment_res.scalars().first()

    if not payment:
        payment = Payment(
            user_id=current_user.id,
            event_id=event.id,
            plan=event.plan,
            status="pending",
        )
        db.add(payment)

    # Update payment details
    payment.status = payload.status
    if payload.order_id:
        payment.order_id = payload.order_id
    if payload.razorpay_payment_id:
        payment.razorpay_payment_id = payload.razorpay_payment_id

    # If payment succeeded, activate the event
    if payload.status == "success":
        event.status = "active"
        db.add(event)

    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    await db.refresh(event)

    return PaymentResponse(
        id=payment.id,
        user_id=payment.user_id,
        event_id=payment.event_id,
        plan=payment.plan,
        amount=payment.amount,
        status=payment.status,
        order_id=payment.order_id,
        razorpay_payment_id=payment.razorpay_payment_id,
        created_at=payment.created_at,
        event_status=event.status,
    )


@router.patch("/{payment_id}/status", response_model=PaymentResponse)
async def update_payment_status_by_id(
    payment_id: uuid.UUID,
    payload: PaymentStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """
    Updates a payment record directly by its payment ID.
    """
    payment_res = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = payment_res.scalar_one_or_none()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment record not found.",
        )

    if payment.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this payment.",
        )

    payment.status = payload.status
    if payload.order_id:
        payment.order_id = payload.order_id
    if payload.razorpay_payment_id:
        payment.razorpay_payment_id = payload.razorpay_payment_id

    event_status: str | None = None
    if payment.event_id:
        event_res = await db.execute(select(Event).where(Event.id == payment.event_id))
        event = event_res.scalar_one_or_none()
        if event:
            if payload.status == "success":
                event.status = "active"
                db.add(event)
            event_status = event.status

    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    return PaymentResponse(
        id=payment.id,
        user_id=payment.user_id,
        event_id=payment.event_id,
        plan=payment.plan,
        amount=payment.amount,
        status=payment.status,
        order_id=payment.order_id,
        razorpay_payment_id=payment.razorpay_payment_id,
        created_at=payment.created_at,
        event_status=event_status,
    )


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_record(
    payload: PaymentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """
    Explicitly creates a new pending payment record for an event.
    """
    event_res = await db.execute(select(Event).where(Event.id == payload.event_id))
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    if event.host_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create payments for this event.",
        )

    payment = Payment(
        user_id=current_user.id,
        event_id=payload.event_id,
        plan=payload.plan,
        amount=payload.amount,
        order_id=payload.order_id,
        status="pending",
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    return PaymentResponse(
        id=payment.id,
        user_id=payment.user_id,
        event_id=payment.event_id,
        plan=payment.plan,
        amount=payment.amount,
        status=payment.status,
        order_id=payment.order_id,
        razorpay_payment_id=payment.razorpay_payment_id,
        created_at=payment.created_at,
        event_status=event.status,
    )
