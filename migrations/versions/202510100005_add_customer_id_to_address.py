"""add customer_id foreign key to customer_address

Revision ID: 202510100005
Revises: 202510100004
Create Date: 2025-10-10

Adds customer_id foreign key to customer_address table to properly link addresses to customers.
The supplier_id is kept for legacy reasons but customer_id becomes the primary relationship.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "202510100005"
down_revision = "202510100004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add customer_id column
    op.add_column(
        "customer_address",
        sa.Column("customer_id", UUID(as_uuid=True), nullable=True, comment="Foreign key to customer table"),
    )

    # Populate customer_id from existing data
    # Find the customer.id where customer.erp_customer_id = customer_address.erp_customer_id
    op.execute("""
        UPDATE customer_address ca
        SET customer_id = c.id
        FROM customer c
        WHERE c.erp_customer_id = ca.erp_customer_id
    """)

    # Now make customer_id NOT NULL since all addresses should have a customer
    op.alter_column("customer_address", "customer_id", nullable=False)

    # Add foreign key constraint
    op.create_foreign_key(
        "fk_customer_address_customer_id",
        "customer_address",
        "customer",
        ["customer_id"],
        ["id"],
        ondelete="CASCADE"
    )

    # Create index for customer_id lookups
    op.create_index("idx_customer_address_customer_id", "customer_address", ["customer_id"], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index("idx_customer_address_customer_id", table_name="customer_address")

    # Drop foreign key
    op.drop_constraint("fk_customer_address_customer_id", "customer_address", type_="foreignkey")

    # Drop column
    op.drop_column("customer_address", "customer_id")
