"""allow supplier admin role"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "202410150004"
down_revision = "202410080003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("role_valid", "user", type_="check")
    op.create_check_constraint(
        "role_valid",
        "user",
        "role in ('reseller','agent','viewer','wholesale_admin','supplier_admin','wholesaler_helpdesk','super_admin')",
    )


def downgrade() -> None:
    op.drop_constraint("role_valid", "user", type_="check")
    op.create_check_constraint(
        "role_valid",
        "user",
        "role in ('reseller','agent','viewer','wholesale_admin','wholesaler_helpdesk','super_admin')",
    )
