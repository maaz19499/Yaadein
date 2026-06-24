from datetime import datetime
import uuid
from sqlalchemy import String, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal
from src.models.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    plan: Mapped[str | None] = mapped_column(String, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)  # CHECK status IN ('pending', 'success', 'failed', 'refunded')
    upgrade_trigger: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
