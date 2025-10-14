"""add customer address BMS integration fields

Revision ID: 202510100002
Revises: 202510100001
Create Date: 2025-10-10

Adds HIGH and MEDIUM priority fields from BMS ERP integration for customer addresses.
Uses English field names (e.g., is_billing_address, is_shipping_address) not BMS originals.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "202510100002"
down_revision = "202510100001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # HIGH Priority Fields
    op.add_column(
        "customer_address",
        sa.Column("address_code", sa.String(), nullable=True, comment="Internal address code (BMS: cindi_dclie)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("public_address_code", sa.String(), nullable=True, comment="Public code shown on documents (BMS: ncocg_dcntr)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("province", sa.String(2), nullable=True, comment="Province code 2 chars (BMS: cprov)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("municipality", sa.String(), nullable=True, comment="Municipality/comune (BMS: rcomu)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("phone", sa.String(), nullable=True, comment="Main phone number (BMS: cntel)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("email", sa.String(), nullable=True, comment="Email address (BMS: tinte_semai)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("pricelist_type", sa.String(), nullable=True, comment="Price list type (BMS: ctipo_dlist)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("payment_terms_code", sa.String(), nullable=True, comment="Payment terms code (BMS: cmpag)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("is_billing_address", sa.Boolean(), nullable=True, comment="Billing address flag (BMS: busat_xfatt)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("is_shipping_address", sa.Boolean(), nullable=True, comment="Shipping address flag (BMS: busat_xinme)"),
    )

    # MEDIUM Priority Fields
    op.add_column(
        "customer_address",
        sa.Column("street_name", sa.String(), nullable=True, comment="Street name separated (BMS: rviaa_dstra)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("street_number", sa.String(), nullable=True, comment="Street number (BMS: cnciv_dstra)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("internal_number", sa.String(), nullable=True, comment="Internal/apartment number (BMS: cnint_dstra)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("region", sa.String(), nullable=True, comment="Region code (BMS: cregi)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("zone_code", sa.String(), nullable=True, comment="Geographic zone (BMS: czona)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("mobile_phone", sa.String(), nullable=True, comment="Mobile/additional phone (BMS: cntel_sagg1)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("fax", sa.String(), nullable=True, comment="Fax number (BMS: cntel_sfaxx)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("website", sa.String(), nullable=True, comment="Website URL (BMS: tinte_ssito)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("latitude", sa.Numeric(precision=10, scale=8), nullable=True, comment="GPS latitude (BMS: qcoox)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("longitude", sa.Numeric(precision=11, scale=8), nullable=True, comment="GPS longitude (BMS: qcooy)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("promo_pricelist_code", sa.String(), nullable=True, comment="Promotional pricelist (BMS: clist_sprom)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("shipping_terms", sa.String(), nullable=True, comment="Shipping/port terms (BMS: cport)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("transport_type", sa.String(), nullable=True, comment="Transport type (BMS: ctras)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("language_code", sa.String(10), nullable=True, comment="Language code (BMS: cling)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("currency_code", sa.String(10), nullable=True, comment="Currency code (BMS: cvalu)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("carrier_code", sa.String(), nullable=True, comment="Carrier/shipper code (BMS: canag_svett)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("is_payment_address", sa.Boolean(), nullable=True, comment="Payment address flag (BMS: busat_xpaga)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("is_delivery_address", sa.Boolean(), nullable=True, comment="Delivery address flag (BMS: busat_xsdlg)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("registration_date", sa.DateTime(timezone=True), nullable=True, comment="Address registration date (BMS: iindi_dclie)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("iban", sa.String(34), nullable=True, comment="IBAN code (BMS: cabix)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("bic_swift", sa.String(11), nullable=True, comment="BIC/SWIFT code (BMS: ccabx)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("discount_1", sa.Numeric(precision=5, scale=3), nullable=True, comment="Discount percentage 1 (BMS: pscon_orica_1)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("discount_2", sa.Numeric(precision=5, scale=3), nullable=True, comment="Discount percentage 2 (BMS: pscon_orica_2)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("agent_code", sa.String(), nullable=True, comment="Sales agent code (BMS: canag_sagen)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("sales_point_code", sa.String(), nullable=True, comment="Sales point code (BMS: cpven)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("vat_code", sa.String(), nullable=True, comment="VAT exemption code (BMS: caiva)"),
    )
    op.add_column(
        "customer_address",
        sa.Column("credit_limit", sa.Numeric(precision=12, scale=2), nullable=True, comment="Credit limit for this address (BMS: afido_dclie)"),
    )

    # Create indexes for lookups
    op.create_index("idx_address_address_code", "customer_address", ["address_code"], unique=False)
    op.create_index("idx_address_public_code", "customer_address", ["public_address_code"], unique=False)
    op.create_index("idx_address_email", "customer_address", ["email"], unique=False)
    op.create_index("idx_address_phone", "customer_address", ["phone"], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_address_phone", table_name="customer_address")
    op.drop_index("idx_address_email", table_name="customer_address")
    op.drop_index("idx_address_public_code", table_name="customer_address")
    op.drop_index("idx_address_address_code", table_name="customer_address")

    # Drop MEDIUM priority columns
    op.drop_column("customer_address", "credit_limit")
    op.drop_column("customer_address", "vat_code")
    op.drop_column("customer_address", "sales_point_code")
    op.drop_column("customer_address", "agent_code")
    op.drop_column("customer_address", "discount_2")
    op.drop_column("customer_address", "discount_1")
    op.drop_column("customer_address", "bic_swift")
    op.drop_column("customer_address", "iban")
    op.drop_column("customer_address", "registration_date")
    op.drop_column("customer_address", "is_delivery_address")
    op.drop_column("customer_address", "is_payment_address")
    op.drop_column("customer_address", "carrier_code")
    op.drop_column("customer_address", "currency_code")
    op.drop_column("customer_address", "language_code")
    op.drop_column("customer_address", "transport_type")
    op.drop_column("customer_address", "shipping_terms")
    op.drop_column("customer_address", "promo_pricelist_code")
    op.drop_column("customer_address", "longitude")
    op.drop_column("customer_address", "latitude")
    op.drop_column("customer_address", "website")
    op.drop_column("customer_address", "fax")
    op.drop_column("customer_address", "mobile_phone")
    op.drop_column("customer_address", "zone_code")
    op.drop_column("customer_address", "region")
    op.drop_column("customer_address", "internal_number")
    op.drop_column("customer_address", "street_number")
    op.drop_column("customer_address", "street_name")

    # Drop HIGH priority columns
    op.drop_column("customer_address", "is_shipping_address")
    op.drop_column("customer_address", "is_billing_address")
    op.drop_column("customer_address", "payment_terms_code")
    op.drop_column("customer_address", "pricelist_type")
    op.drop_column("customer_address", "email")
    op.drop_column("customer_address", "phone")
    op.drop_column("customer_address", "municipality")
    op.drop_column("customer_address", "province")
    op.drop_column("customer_address", "public_address_code")
    op.drop_column("customer_address", "address_code")
