"""remove supplier_id from customer_address

Revision ID: 202510100006
Revises: 202510100005
Create Date: 2025-10-10

Removes supplier_id from customer_address since addresses belong to customers
and customers already have supplier_id. This eliminates redundancy.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "202510100006"
down_revision = "202510100005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop index first (conditionally)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'customer_address'
                AND indexname = 'idx_customer_address_supplier'
            ) THEN
                DROP INDEX idx_customer_address_supplier;
            END IF;
        END $$;
    """)

    # Drop foreign key constraint (find and drop by pattern match)
    op.execute("""
        DO $$
        DECLARE
            constraint_name TEXT;
        BEGIN
            SELECT tc.constraint_name INTO constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'customer_address'
            AND tc.constraint_type = 'FOREIGN KEY'
            AND kcu.column_name = 'supplier_id'
            LIMIT 1;

            IF constraint_name IS NOT NULL THEN
                EXECUTE 'ALTER TABLE customer_address DROP CONSTRAINT ' || quote_ident(constraint_name);
            END IF;
        END $$;
    """)

    # Drop the column (only if it exists)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'customer_address'
                AND column_name = 'supplier_id'
            ) THEN
                ALTER TABLE customer_address DROP COLUMN supplier_id;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Add column back
    op.add_column(
        "customer_address",
        sa.Column("supplier_id", UUID(as_uuid=True), nullable=True),
    )

    # Populate supplier_id from customer.supplier_id
    op.execute("""
        UPDATE customer_address ca
        SET supplier_id = c.supplier_id
        FROM customer c
        WHERE c.id = ca.customer_id
    """)

    # Make NOT NULL
    op.alter_column("customer_address", "supplier_id", nullable=False)

    # Re-add foreign key
    op.create_foreign_key(
        "customer_address_supplier_id_fkey",
        "customer_address",
        "supplier",
        ["supplier_id"],
        ["id"],
        ondelete="CASCADE"
    )

    # Re-add index
    op.create_index("idx_customer_address_supplier", "customer_address", ["supplier_id"], unique=False)
