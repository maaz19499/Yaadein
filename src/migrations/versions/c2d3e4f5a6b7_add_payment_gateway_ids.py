"""add_payment_gateway_ids

Revision ID: c2d3e4f5a6b7
Revises: b1a2c3d4e5f6
Create Date: 2026-09-12 00:00:00.000000

"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add order_id and razorpay_payment_id columns to payments table."""
    op.execute("""
        ALTER TABLE payments 
        ADD COLUMN IF NOT EXISTS order_id text UNIQUE,
        ADD COLUMN IF NOT EXISTS razorpay_payment_id text;
        CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
    """)


def downgrade() -> None:
    """Remove order_id and razorpay_payment_id columns from payments table."""
    op.execute("""
        DROP INDEX IF EXISTS idx_payments_order_id;
        ALTER TABLE payments 
        DROP COLUMN IF EXISTS order_id,
        DROP COLUMN IF EXISTS razorpay_payment_id;
    """)
