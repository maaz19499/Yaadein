"""remove_auth_provider_column

Revision ID: a92f81c92d34
Revises: 843d5a950752
Create Date: 2026-07-30 19:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a92f81c92d34"
down_revision: Union[str, Sequence[str], None] = "843d5a950752"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("users", schema="public")]
    if "auth_provider" in columns:
        op.drop_column("users", "auth_provider", schema="public")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("users", schema="public")]
    if "auth_provider" not in columns:
        op.add_column(
            "users",
            sa.Column("auth_provider", sa.String(), nullable=True),
            schema="public",
        )
