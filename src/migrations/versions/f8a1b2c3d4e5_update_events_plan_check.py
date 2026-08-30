"""update_events_plan_check

Revision ID: f8a1b2c3d4e5
Revises: e7f1a2b3c4d5
Create Date: 2026-08-29 16:42:00.000000

"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f8a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e7f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update events_plan_check constraint to include starter, free, and elite tiers."""
    op.execute("""
        ALTER TABLE events DROP CONSTRAINT IF EXISTS events_plan_check;
        ALTER TABLE events ADD CONSTRAINT events_plan_check 
            CHECK (plan IN ('starter', 'free', 'basic', 'premium', 'elite', 'professional'));
    """)


def downgrade() -> None:
    """Revert events_plan_check constraint to legacy tiers."""
    op.execute("""
        ALTER TABLE events DROP CONSTRAINT IF EXISTS events_plan_check;
        ALTER TABLE events ADD CONSTRAINT events_plan_check 
            CHECK (plan IN ('basic', 'premium', 'professional'));
    """)
