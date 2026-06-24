from datetime import datetime
import uuid
from typing import Any
from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    PrimaryKeyConstraint,
    ForeignKeyConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        PrimaryKeyConstraint("event_id", "id"),
        {
            "postgresql_partition_by": "HASH (event_id)",
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # CHECK (type IN ('static', 'dynamic'))
    dynamic_filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AlbumMedia(Base):
    __tablename__ = "album_media"
    __table_args__ = (
        PrimaryKeyConstraint("event_id", "album_id", "media_id"),
        ForeignKeyConstraint(
            ["event_id", "album_id"],
            ["albums.event_id", "albums.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["event_id", "media_id"],
            ["media.event_id", "media.id"],
            ondelete="CASCADE",
        ),
        {
            "postgresql_partition_by": "HASH (event_id)",
        },
    )

    event_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    album_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    media_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
