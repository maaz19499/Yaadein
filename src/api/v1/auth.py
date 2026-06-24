from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.event import Event
from src.models.face import FaceConsent, FaceEmbedding
from src.models.guest import Guest
from src.schemas.user import GuestCreate, GuestResponse, GuestResponseData

router = APIRouter(tags=["guests"])


@router.post("/{event_id}/guests", response_model=GuestResponse)
async def register_guest(
    event_id: uuid.UUID,
    guest_in: GuestCreate,
    db: AsyncSession = Depends(get_db),
) -> GuestResponse:
    # 1. Verify event exists
    event_result = await db.execute(select(Event).where(Event.id == event_id))
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # 2. Check if guest already exists for this event
    guest_result = await db.execute(
        select(Guest).where(
            Guest.event_id == event_id,
            Guest.guest_session_id == guest_in.guest_session_id,
        )
    )
    guest = guest_result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if guest:
        # Update guest details and touch last_seen_at
        guest.name = guest_in.name
        guest.phone = guest_in.phone
        guest.last_seen_at = now
    else:
        # Create new guest row
        guest = Guest(
            event_id=event_id,
            guest_session_id=guest_in.guest_session_id,
            name=guest_in.name,
            phone=guest_in.phone,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(guest)

    # Flush so foreign key constraint to guest row is satisfied before inserting consent
    await db.flush()

    # 3. Handle Face Consent
    consent_result = await db.execute(
        select(FaceConsent).where(
            FaceConsent.event_id == event_id,
            FaceConsent.guest_session_id == guest_in.guest_session_id,
        )
    )
    consent = consent_result.scalar_one_or_none()

    should_backfill = False
    if guest_in.face_search_consent:
        if consent:
            # Re-consent or update details
            consent.consent_given_at = now
            consent.consent_revoked_at = None
            consent.purge_executed_at = None
            consent.guest_name = guest_in.name
        else:
            # Create new consent record
            consent = FaceConsent(
                event_id=event_id,
                guest_session_id=guest_in.guest_session_id,
                guest_name=guest_in.name,
                consent_given_at=now,
            )
            db.add(consent)
        # If they just enabled consent or update it, prepare to backfill
        should_backfill = True
    else:
        # Consent is false / revoked
        if consent:
            consent.consent_revoked_at = now
            # Immediately delete any existing face embeddings for this consent to comply with DPDP
            await db.execute(
                delete(FaceEmbedding).where(
                    FaceEmbedding.uploader_consent_id == consent.id
                )
            )

    await db.commit()

    # If consent was granted and event has face search enabled, back-fill embeddings for any existing visible media uploaded by this guest
    if should_backfill and consent and event.face_search_enabled:
        from src.models.media import Media
        from src.workers.tasks.face import generate_face_embeddings

        media_result = await db.execute(
            select(Media).where(
                Media.event_id == event_id,
                Media.guest_session_id == guest_in.guest_session_id,
                Media.status == "visible",
            )
        )
        visible_medias = media_result.scalars().all()
        for m in visible_medias:
            generate_face_embeddings.delay(str(event_id), str(m.id), str(consent.id))

    # Determine response consent status
    # Active if consent exists and has not been revoked
    consent_active = (
        guest_in.face_search_consent
        if consent and consent.consent_revoked_at is None
        else False
    )

    return GuestResponse(
        status="success",
        guest=GuestResponseData(
            guest_session_id=guest_in.guest_session_id,
            name=guest_in.name,
            face_search_consent=consent_active,
        ),
    )
