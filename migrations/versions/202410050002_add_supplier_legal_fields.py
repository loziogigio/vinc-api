"""add supplier legal fields"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202410050002"
down_revision = "202410050001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplier", sa.Column("legal_name", sa.String(), nullable=True))
    op.add_column("supplier", sa.Column("legal_address", sa.Text(), nullable=True))
    op.add_column("supplier", sa.Column("legal_details", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("supplier", "legal_details")
    op.drop_column("supplier", "legal_address")
    op.drop_column("supplier", "legal_name")
