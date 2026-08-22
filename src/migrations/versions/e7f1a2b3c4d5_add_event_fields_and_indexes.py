"""add_event_fields_and_indexes

Revision ID: e7f1a2b3c4d5
Revises: a92f81c92d34
Create Date: 2026-08-22 14:38:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "a92f81c92d34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add event metadata columns to events table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("events", schema="public")]

    if "name" not in existing_columns:
        op.add_column("events", sa.Column("name", sa.String(100), nullable=True))
    if "type" not in existing_columns:
        op.add_column("events", sa.Column("type", sa.String(50), nullable=True))
    if "date" not in existing_columns:
        op.add_column("events", sa.Column("date", sa.DateTime(timezone=True), nullable=True))
    if "city" not in existing_columns:
        op.add_column("events", sa.Column("city", sa.String(100), nullable=True))
    if "cover_photo_url" not in existing_columns:
        op.add_column("events", sa.Column("cover_photo_url", sa.String(), nullable=True))
    if "status" not in existing_columns:
        op.add_column(
            "events",
            sa.Column("status", sa.String(20), server_default="pending", nullable=True),
        )
    if "guest_pin" not in existing_columns:
        op.add_column("events", sa.Column("guest_pin", sa.String(4), nullable=True))


def downgrade() -> None:
    """Remove event metadata columns."""
    op.drop_column("events", "guest_pin")
    op.drop_column("events", "status")
    op.drop_column("events", "cover_photo_url")
    op.drop_column("events", "city")
    op.drop_column("events", "date")
    op.drop_column("events", "type")
    op.drop_column("events", "name")
