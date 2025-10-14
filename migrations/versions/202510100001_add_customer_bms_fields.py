"""add customer BMS integration fields

Revision ID: 202510100001
Revises: 202410150004
Create Date: 2025-10-10

Adds HIGH and MEDIUM priority fields from BMS ERP integration for customers.
Uses English field names (e.g., is_billing_address) not BMS originals.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "202510100001"
down_revision = "202410150004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # HIGH Priority Fields
    op.add_column(
        "customer",
        sa.Column("customer_code", sa.String(), nullable=True, comment="Internal customer code (BMS: canag_sclie)"),
    )
    op.add_column(
        "customer",
        sa.Column("public_customer_code", sa.String(), nullable=True, comment="Public code shown on invoices (BMS: ncocg)"),
    )
    op.add_column(
        "customer",
        sa.Column("business_name", sa.String(), nullable=True, comment="Full business/trade name (BMS: traso)"),
    )
    op.add_column(
        "customer",
        sa.Column("first_name", sa.String(), nullable=True, comment="First name for individuals (BMS: rnome)"),
    )
    op.add_column(
        "customer",
        sa.Column("last_name", sa.String(), nullable=True, comment="Last name for individuals (BMS: rcogn)"),
    )
    op.add_column(
        "customer",
        sa.Column("fiscal_code", sa.String(16), nullable=True, comment="Italian tax code - codice fiscale (BMS: cfisc)"),
    )
    op.add_column(
        "customer",
        sa.Column("vat_number", sa.String(11), nullable=True, comment="Italian VAT number - P.IVA (BMS: cpiva)"),
    )
    op.add_column(
        "customer",
        sa.Column("registration_date", sa.DateTime(timezone=True), nullable=True, comment="Initial registration date (BMS: ianag_sclie)"),
    )
    op.add_column(
        "customer",
        sa.Column("credit_limit", sa.Numeric(precision=12, scale=2), nullable=True, comment="Credit limit amount (BMS: asogl_xivas)"),
    )

    # MEDIUM Priority Fields
    op.add_column(
        "customer",
        sa.Column("customer_category", sa.String(), nullable=True, comment="Customer category/classification (BMS: ccate_sclie)"),
    )
    op.add_column(
        "customer",
        sa.Column("activity_category", sa.String(), nullable=True, comment="Activity/industry sector (BMS: ccate_satti)"),
    )
    op.add_column(
        "customer",
        sa.Column("gender", sa.String(1), nullable=True, comment="Gender M/F/O (BMS: csess)"),
    )
    op.add_column(
        "customer",
        sa.Column("business_start_date", sa.DateTime(timezone=True), nullable=True, comment="Business activity start date (BMS: dinse_ianag)"),
    )
    op.add_column(
        "customer",
        sa.Column("financial_status", sa.String(), nullable=True, comment="Financial status code (BMS: cstat_dfiac)"),
    )
    op.add_column(
        "customer",
        sa.Column("cash_payment", sa.Boolean(), nullable=True, comment="Cash payment preference (BMS: bcafl)"),
    )
    op.add_column(
        "customer",
        sa.Column("auto_packaging", sa.Boolean(), nullable=True, comment="Auto packaging flag (BMS: bragg_ximba)"),
    )
    op.add_column(
        "customer",
        sa.Column("customer_group", sa.String(), nullable=True, comment="Customer group name (BMS: tclie_ngrup)"),
    )

    # Add constraints
    op.create_check_constraint(
        "customer_gender_valid",
        "customer",
        "gender IS NULL OR gender IN ('M', 'F', 'O')",
    )

    # Create indexes for lookups
    op.create_index("idx_customer_customer_code", "customer", ["customer_code"], unique=False)
    op.create_index("idx_customer_public_code", "customer", ["public_customer_code"], unique=False)
    op.create_index("idx_customer_fiscal_code", "customer", ["fiscal_code"], unique=False)
    op.create_index("idx_customer_vat_number", "customer", ["vat_number"], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_customer_vat_number", table_name="customer")
    op.drop_index("idx_customer_fiscal_code", table_name="customer")
    op.drop_index("idx_customer_public_code", table_name="customer")
    op.drop_index("idx_customer_customer_code", table_name="customer")

    # Drop constraint
    op.drop_constraint("customer_gender_valid", "customer", type_="check")

    # Drop MEDIUM priority columns
    op.drop_column("customer", "customer_group")
    op.drop_column("customer", "auto_packaging")
    op.drop_column("customer", "cash_payment")
    op.drop_column("customer", "financial_status")
    op.drop_column("customer", "business_start_date")
    op.drop_column("customer", "gender")
    op.drop_column("customer", "activity_category")
    op.drop_column("customer", "customer_category")

    # Drop HIGH priority columns
    op.drop_column("customer", "credit_limit")
    op.drop_column("customer", "registration_date")
    op.drop_column("customer", "vat_number")
    op.drop_column("customer", "fiscal_code")
    op.drop_column("customer", "last_name")
    op.drop_column("customer", "first_name")
    op.drop_column("customer", "business_name")
    op.drop_column("customer", "public_customer_code")
    op.drop_column("customer", "customer_code")
