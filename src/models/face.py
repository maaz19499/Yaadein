from datetime import datetime
import uuid
from sqlalchemy import String, DateTime, ForeignKey, ForeignKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from src.models.base import Base


class FaceConsent(Base):
    __tablename__ = "face_consents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "guest_session_id"],
            ["guests.event_id", "guests.guest_session_id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    guest_session_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    guest_name: Mapped[str | None] = mapped_column(String, nullable=True)
    consent_given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FaceCluster(Base):
    __tablename__ = "face_clusters"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    matched_guest_session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    matched_guest_name: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "media_id"],
            ["media.event_id", "media.id"],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    media_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("face_clusters.id", ondelete="SET NULL"), nullable=True)
    uploader_consent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("face_consents.id", ondelete="CASCADE"), nullable=False)
    purge_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
