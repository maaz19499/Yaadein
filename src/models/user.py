from datetime import datetime
import uuid
from typing import Any
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base


class AuthUser(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_user_meta_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True)
    phone: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str | None] = mapped_column(String, nullable=True)  # CHECK (role IN ('host', 'photographer', 'admin'))
    auth_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
