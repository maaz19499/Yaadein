"""add_upload_expiry_to_events

Revision ID: 843d5a950752
Revises: 48c64c1f86af
Create Date: 2026-06-28 13:59:46.177201

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '843d5a950752'
down_revision: Union[str, Sequence[str], None] = '48c64c1f86af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("events")]

    if "upload_expires_at" not in columns:
        op.add_column(
            "events",
            sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "face_clustered" not in columns:
        op.add_column(
            "events",
            sa.Column(
                "face_clustered",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )



def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("events", "face_clustered")
    op.drop_column("events", "upload_expires_at")
