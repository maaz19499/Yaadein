from datetime import datetime
import uuid
from sqlalchemy import String, DateTime, ForeignKey, PrimaryKeyConstraint, UniqueConstraint, ForeignKeyConstraint, CheckConstraint, BigInteger, Integer, func
from sqlalchemy.dialects.postgresql import BIT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.base import Base


class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        PrimaryKeyConstraint("event_id", "id"),
        UniqueConstraint("event_id", "idempotency_key"),
        ForeignKeyConstraint(
            ["event_id", "guest_session_id"],
            ["guests.event_id", "guests.guest_session_id"],
            ondelete="SET NULL",
        ),
        CheckConstraint("(uploaded_by IS NOT NULL) OR (guest_session_id IS NOT NULL)"),
        {
            "postgresql_partition_by": "HASH (event_id)",
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)  # CHECK (type IN ('image', 'video'))
    r2_object_key: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)  # CHECK status IN ('pending_verify', 'scanning', 'processing', 'visible', 'rejected', 'duplicate')
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String, nullable=True)
    phash: Mapped[str | None] = mapped_column(BIT(64), nullable=True)  # Stored as BIT(64), handled as 64-char binary string
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @classmethod
    async def find_duplicates(
        cls,
        session: AsyncSession,
        event_id: uuid.UUID,
        incoming_phash: str,
        threshold: int = 10,
    ) -> list[uuid.UUID]:
        """
        Find duplicate media records within the same event using bitwise XOR `#`
        and `bit_count` function (Hamming distance) in Postgres.
        """
        from sqlalchemy import text
        query = text(
            "SELECT id FROM media "
            "WHERE event_id = :event_id "
            "AND status = 'visible' "
            "AND bit_count(phash # :incoming_phash) <= :threshold"
        )
        result = await session.execute(
            query,
            {
                "event_id": event_id,
                "incoming_phash": incoming_phash,
                "threshold": threshold,
            }
        )
        return [row[0] for row in result.fetchall()]


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scope: Mapped[str | None] = mapped_column(String, nullable=True)  # CHECK scope IN ('single', 'album', 'full_event')
    status: Mapped[str | None] = mapped_column(String, nullable=True)  # CHECK status IN ('queued', 'processing', 'ready', 'failed')
    download_url: Mapped[str | None] = mapped_column(String, nullable=True)
