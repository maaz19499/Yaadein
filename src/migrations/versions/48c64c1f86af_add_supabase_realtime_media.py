"""add_supabase_realtime_media

Revision ID: 48c64c1f86af
Revises: cbc3142fffb5
Create Date: 2026-06-24 17:52:18.832604

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48c64c1f86af'
down_revision: Union[str, Sequence[str], None] = 'cbc3142fffb5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    DO $$
    BEGIN
        -- Check if publication exists, if not create it
        IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
            CREATE PUBLICATION supabase_realtime;
        END IF;
        
        -- Check if table is already in publication to avoid duplicate errors
        IF NOT EXISTS (
            SELECT 1 
            FROM pg_publication_rel pr 
            JOIN pg_class c ON pr.prrelid = c.oid 
            JOIN pg_publication p ON pr.prpubid = p.oid 
            WHERE p.pubname = 'supabase_realtime' 
              AND c.relname = 'media'
        ) THEN
            ALTER PUBLICATION supabase_realtime ADD TABLE media;
        END IF;
    END;
    $$;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 
            FROM pg_publication_rel pr 
            JOIN pg_class c ON pr.prrelid = c.oid 
            JOIN pg_publication p ON pr.prpubid = p.oid 
            WHERE p.pubname = 'supabase_realtime' 
              AND c.relname = 'media'
        ) THEN
            ALTER PUBLICATION supabase_realtime DROP TABLE media;
        END IF;
    END;
    $$;
    """)
