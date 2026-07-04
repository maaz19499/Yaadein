from datetime import datetime
import uuid
from typing import Any
from sqlalchemy import String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    host_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    face_search_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # CHECK plan IN ('basic', 'premium', 'professional')
    storage_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    upload_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    face_clustered: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_wedding: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GalleryCache(Base):
    __tablename__ = "gallery_cache"

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    cached_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class QRCode(Base):
    __tablename__ = "qr_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    scan_count: Mapped[int] = mapped_column(default=0)
    unique_visitors: Mapped[int] = mapped_column(default=0)
