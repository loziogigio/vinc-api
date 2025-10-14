"""add customer contact fields

Revision ID: 202510100003
Revises: 202510100002
Create Date: 2025-10-10

Adds contact_email and contact_phone fields to customer table.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "202510100003"
down_revision = "202510100002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add contact fields
    op.add_column(
        "customer",
        sa.Column("contact_email", sa.String(), nullable=True, comment="Contact email address"),
    )
    op.add_column(
        "customer",
        sa.Column("contact_phone", sa.String(), nullable=True, comment="Contact phone number"),
    )

    # Create index for email lookups
    op.create_index("idx_customer_contact_email", "customer", ["contact_email"], unique=False)


def downgrade() -> None:
    # Drop index
    op.drop_index("idx_customer_contact_email", table_name="customer")

    # Drop columns
    op.drop_column("customer", "contact_phone")
    op.drop_column("customer", "contact_email")
