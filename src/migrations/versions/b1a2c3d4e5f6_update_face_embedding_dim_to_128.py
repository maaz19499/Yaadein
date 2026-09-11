"""update_face_embedding_dim_to_128

Revision ID: b1a2c3d4e5f6
Revises: f8a1b2c3d4e5
Create Date: 2026-09-11 22:45:00.000000

"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f8a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update face_embeddings.embedding vector dimension from 512 to 128 for SFace."""
    op.execute("""
        DROP INDEX IF EXISTS idx_face_embeddings_hnsw;
        ALTER TABLE face_embeddings ALTER COLUMN embedding TYPE vector(128);
        CREATE INDEX IF NOT EXISTS idx_face_embeddings_hnsw 
            ON face_embeddings USING hnsw (embedding vector_cosine_ops);
    """)


def downgrade() -> None:
    """Revert face_embeddings.embedding vector dimension to 512."""
    op.execute("""
        DROP INDEX IF EXISTS idx_face_embeddings_hnsw;
        ALTER TABLE face_embeddings ALTER COLUMN embedding TYPE vector(512);
        CREATE INDEX IF NOT EXISTS idx_face_embeddings_hnsw 
            ON face_embeddings USING hnsw (embedding vector_cosine_ops);
    """)
