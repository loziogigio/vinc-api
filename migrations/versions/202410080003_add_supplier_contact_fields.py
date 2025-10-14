"""add supplier contact fields"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202410080003"
down_revision = "202410050002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplier", sa.Column("legal_email", sa.String(length=255), nullable=True))
    op.add_column("supplier", sa.Column("legal_number", sa.String(length=64), nullable=True))
    op.add_column("supplier", sa.Column("tax_id", sa.String(length=64), nullable=True))
    op.add_column(
        "supplier",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    # Populate tax_id from legacy legal_details if present, truncating to fit the new column
    op.execute(
        "UPDATE supplier SET tax_id = LEFT(TRIM(legal_details), 64) WHERE legal_details IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("supplier", "status")
    op.drop_column("supplier", "tax_id")
    op.drop_column("supplier", "legal_number")
    op.drop_column("supplier", "legal_email")
