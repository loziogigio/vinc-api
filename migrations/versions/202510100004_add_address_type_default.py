"""add address type and is_default fields

Revision ID: 202510100004
Revises: 202510100003
Create Date: 2025-10-10

Adds type and is_default fields to customer_address table.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "202510100004"
down_revision = "202510100003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add type and is_default fields
    op.add_column(
        "customer_address",
        sa.Column("type", sa.String(), nullable=True, comment="Address type (billing, shipping, etc)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("is_default", sa.Boolean(), nullable=True, comment="Whether this is the default address"),
    )

    # Create index for type lookups
    op.create_index("idx_address_type", "customer_address", ["type"], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index("idx_address_type", table_name="customer_address")

    # Drop columns
    op.drop_column("customer_address", "is_default")
    op.drop_column("customer_address", "type")
