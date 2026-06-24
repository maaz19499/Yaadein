from datetime import datetime, timedelta, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.database import get_db
from src.models.event import Event
from src.models.user import User
from src.schemas.event import (
    EventCreate,
    EventPublicResponse,
    EventResponse,
    EventUpdate,
)

router = APIRouter(tags=["events"])


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event_in: EventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Event:
    # Check that current user is host, photographer, or admin
    if current_user.role not in ("host", "photographer", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only hosts, photographers, and admins can create events.",
        )

    # Check for unique slug
    result = await db.execute(select(Event).where(Event.slug == event_in.slug))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An event with this slug already exists.",
        )

    now = datetime.now(timezone.utc)
    # Default plan to basic and storage expires in 30 days
    storage_expires = now + timedelta(days=30)

    event = Event(
        host_id=current_user.id,
        slug=event_in.slug,
        face_search_enabled=event_in.face_search_enabled,
        plan="basic",
        storage_expires_at=storage_expires,
        is_wedding=event_in.is_wedding,
        created_at=now,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("", response_model=list[EventResponse])
async def list_events(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Event]:
    result = await db.execute(
        select(Event)
        .where(Event.host_id == current_user.id)
        .order_by(Event.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/slug/{slug}", response_model=EventPublicResponse)
async def get_event_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> Event:
    result = await db.execute(select(Event).where(Event.slug == slug))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )
    return event


@router.put("/{id}", response_model=EventResponse)
async def update_event(
    id: uuid.UUID,
    event_in: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Event:
    result = await db.execute(select(Event).where(Event.id == id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    # Check that current user is the owner/host of the event (or an admin)
    if event.host_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this event.",
        )

    if event_in.slug is not None and event_in.slug != event.slug:
        # Check slug uniqueness if it changes
        slug_check = await db.execute(select(Event).where(Event.slug == event_in.slug))
        if slug_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An event with this slug already exists.",
            )
        event.slug = event_in.slug

    if event_in.face_search_enabled is not None:
        event.face_search_enabled = event_in.face_search_enabled

    if event_in.is_wedding is not None:
        event.is_wedding = event_in.is_wedding

    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event
