"""create user and wholesale domain tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "202410050001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "customer",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("erp_customer_id", sa.String(), nullable=False),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("erp_customer_id"),
    )

    op.create_table(
        "customer_address",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("erp_address_id", sa.String(), nullable=False),
        sa.Column("erp_customer_id", sa.String(), nullable=False),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("street", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("zip", sa.String(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("pricelist_code", sa.String(), nullable=True),
        sa.Column("channel_code", sa.String(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("erp_customer_id", "erp_address_id"),
    )

    op.create_table(
        "user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'invited'"),
        ),
        sa.Column(
            "auth_provider",
            sa.String(),
            nullable=False,
            server_default=sa.text("'keycloak'"),
        ),
        sa.Column("kc_user_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            server_onupdate=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("kc_user_id"),
        sa.CheckConstraint(
            "role in ('reseller','agent','viewer','wholesale_admin','super_admin')",
            name="role_valid",
        ),
        sa.CheckConstraint(
            "status in ('invited','active','disabled')",
            name="status_valid",
        ),
    )

    op.create_table(
        "user_customer_link",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(),
            nullable=False,
            server_default=sa.text("'buyer'"),
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "customer_id"),
        sa.CheckConstraint(
            "role in ('buyer','viewer')",
            name="role_valid",
        ),
    )

    op.create_table(
        "user_address_link",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "customer_address_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(),
            nullable=False,
            server_default=sa.text("'buyer'"),
        ),
        sa.ForeignKeyConstraint(["customer_address_id"], ["customer_address.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "customer_address_id"),
        sa.CheckConstraint(
            "role in ('buyer','viewer')",
            name="role_valid",
        ),
    )

    op.create_index(
        "idx_customer_address_supplier",
        "customer_address",
        ["supplier_id"],
        unique=False,
    )
    op.create_index(
        "idx_user_customer_user",
        "user_customer_link",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "idx_user_address_user",
        "user_address_link",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_user_address_user", table_name="user_address_link")
    op.drop_index("idx_user_customer_user", table_name="user_customer_link")
    op.drop_index("idx_customer_address_supplier", table_name="customer_address")

    op.drop_table("user_address_link")
    op.drop_table("user_customer_link")
    op.drop_table("user")
    op.drop_table("customer_address")
    op.drop_table("customer")
    op.drop_table("supplier")
