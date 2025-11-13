"""create payment tables

Revision ID: 202511130001
Revises: 202510100006
Create Date: 2025-11-13

Creates payment system tables for multi-tenant payment processing with
support for multiple payment providers (Stripe, PayPal, Nexi, etc.).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

# revision identifiers, used by Alembic.
revision = "202511130001"
down_revision = "202510100006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === TenantPaymentProvider ===
    op.create_table(
        "tenant_payment_provider",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "mode",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'test'"),
        ),
        sa.Column(
            "credentials",
            JSON,
            nullable=False,
            comment="Encrypted credentials for the payment provider",
        ),
        sa.Column(
            "config",
            JSON,
            nullable=False,
            server_default=sa.text("'{}'::json"),
            comment="Provider-specific configuration settings",
        ),
        sa.Column(
            "fee_bearer",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'wholesaler'"),
            comment="Who bears the payment processing fees",
        ),
        sa.Column(
            "fees",
            JSON,
            nullable=False,
            server_default=sa.text("'{}'::json"),
            comment="Fee configuration (percentage, fixed amounts, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_provider"),
        sa.CheckConstraint(
            "provider IN ('stripe', 'paypal', 'nexi', 'banca_sella', 'scalapay', 'bank_transfer')",
            name="provider_valid",
        ),
        sa.CheckConstraint(
            "mode IN ('test', 'live')",
            name="mode_valid",
        ),
        sa.CheckConstraint(
            "fee_bearer IN ('wholesaler', 'retailer', 'customer', 'split')",
            name="fee_bearer_valid",
        ),
    )
    op.create_index(
        "idx_tenant_provider_tenant",
        "tenant_payment_provider",
        ["tenant_id"],
    )
    op.create_index(
        "idx_tenant_provider_enabled",
        "tenant_payment_provider",
        ["is_enabled"],
    )

    # === StorefrontPaymentMethod ===
    op.create_table(
        "storefront_payment_method",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("storefront_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="Denormalized for efficient querying",
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "display_name",
            sa.String(100),
            nullable=True,
            comment="Custom display name for this payment method",
        ),
        sa.Column(
            "display_description",
            sa.String(255),
            nullable=True,
            comment="Custom description shown to customers",
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Sort order for displaying payment methods",
        ),
        sa.Column(
            "conditions",
            JSON,
            nullable=False,
            server_default=sa.text("'{}'::json"),
            comment="Conditions for showing this method (min/max cart amount, etc.)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storefront_id", "provider", name="uq_storefront_provider"
        ),
        sa.CheckConstraint(
            "provider IN ('stripe', 'paypal', 'nexi', 'banca_sella', 'scalapay', 'bank_transfer')",
            name="provider_valid",
        ),
    )
    op.create_index(
        "idx_storefront_method_storefront",
        "storefront_payment_method",
        ["storefront_id"],
    )
    op.create_index(
        "idx_storefront_method_tenant",
        "storefront_payment_method",
        ["tenant_id"],
    )
    op.create_index(
        "idx_storefront_method_enabled",
        "storefront_payment_method",
        ["is_enabled"],
    )

    # === PaymentTransaction ===
    op.create_table(
        "payment_transaction",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("storefront_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "order_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="Reference to the order being paid",
        ),
        sa.Column(
            "provider",
            sa.String(50),
            nullable=False,
            comment="Payment provider used (stripe, paypal, etc.)",
        ),
        sa.Column(
            "provider_transaction_id",
            sa.String(255),
            nullable=True,
            comment="External transaction ID from the provider",
        ),
        sa.Column(
            "provider_payment_intent_id",
            sa.String(255),
            nullable=True,
            comment="Payment intent/session ID from the provider",
        ),
        sa.Column(
            "amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            comment="Transaction amount",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'EUR'"),
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            comment="Current status of the transaction",
        ),
        sa.Column(
            "payment_method_type",
            sa.String(50),
            nullable=True,
            comment="Type of payment method used (card, bank_transfer, bnpl, etc.)",
        ),
        sa.Column("customer_email", sa.String(255), nullable=True),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            JSON,
            nullable=False,
            server_default=sa.text("'{}'::json"),
            comment="Additional metadata (IP, user agent, etc.)",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Error message if the transaction failed",
        ),
        sa.Column(
            "webhook_events",
            JSON,
            nullable=False,
            server_default=sa.text("'[]'::json"),
            comment="Array of webhook events received for this transaction",
        ),
        sa.Column(
            "refunded_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0"),
            comment="Total amount refunded",
        ),
        sa.Column(
            "refund_reason",
            sa.Text(),
            nullable=True,
            comment="Reason for refund if applicable",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the payment was completed (succeeded or failed)",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'requires_action', 'succeeded', 'failed', 'cancelled', 'refunded', 'partially_refunded')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "provider IN ('stripe', 'paypal', 'nexi', 'banca_sella', 'scalapay', 'bank_transfer')",
            name="provider_valid",
        ),
    )
    op.create_index("idx_payment_txn_order", "payment_transaction", ["order_id"])
    op.create_index(
        "idx_payment_txn_provider_id",
        "payment_transaction",
        ["provider_transaction_id"],
    )
    op.create_index(
        "idx_payment_txn_intent_id",
        "payment_transaction",
        ["provider_payment_intent_id"],
    )
    op.create_index("idx_payment_txn_status", "payment_transaction", ["status"])
    op.create_index("idx_payment_txn_tenant", "payment_transaction", ["tenant_id"])
    op.create_index(
        "idx_payment_txn_storefront", "payment_transaction", ["storefront_id"]
    )
    op.create_index(
        "idx_payment_txn_created", "payment_transaction", ["created_at"]
    )
    op.create_index(
        "idx_payment_txn_customer", "payment_transaction", ["customer_id"]
    )

    # === PaymentWebhookLog ===
    op.create_table(
        "payment_webhook_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column(
            "event_type",
            sa.String(100),
            nullable=True,
            comment="Type of webhook event (e.g., payment_intent.succeeded)",
        ),
        sa.Column(
            "event_id",
            sa.String(255),
            nullable=True,
            comment="Provider's unique event ID for deduplication",
        ),
        sa.Column(
            "payload",
            JSON,
            nullable=False,
            comment="Complete webhook payload",
        ),
        sa.Column(
            "signature",
            sa.String(500),
            nullable=True,
            comment="Webhook signature for verification",
        ),
        sa.Column(
            "headers",
            JSON,
            nullable=True,
            comment="HTTP headers from webhook request",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            comment="Processing status (success, failed, pending, duplicate)",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Error message if processing failed",
        ),
        sa.Column(
            "processing_time_ms",
            sa.Integer(),
            nullable=True,
            comment="Time taken to process the webhook in milliseconds",
        ),
        sa.Column(
            "transaction_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="Related payment transaction if found",
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the webhook was processed",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "provider IN ('stripe', 'paypal', 'nexi', 'banca_sella', 'scalapay', 'bank_transfer')",
            name="provider_valid",
        ),
        sa.CheckConstraint(
            "status IN ('success', 'failed', 'pending', 'duplicate')",
            name="status_valid",
        ),
    )
    op.create_index("idx_webhook_log_provider", "payment_webhook_log", ["provider"])
    op.create_index("idx_webhook_log_event_id", "payment_webhook_log", ["event_id"])
    op.create_index("idx_webhook_log_created", "payment_webhook_log", ["created_at"])
    op.create_index(
        "idx_webhook_log_transaction", "payment_webhook_log", ["transaction_id"]
    )
    op.create_index("idx_webhook_log_status", "payment_webhook_log", ["status"])


def downgrade() -> None:
    # Drop PaymentWebhookLog
    op.drop_index("idx_webhook_log_status", table_name="payment_webhook_log")
    op.drop_index("idx_webhook_log_transaction", table_name="payment_webhook_log")
    op.drop_index("idx_webhook_log_created", table_name="payment_webhook_log")
    op.drop_index("idx_webhook_log_event_id", table_name="payment_webhook_log")
    op.drop_index("idx_webhook_log_provider", table_name="payment_webhook_log")
    op.drop_table("payment_webhook_log")

    # Drop PaymentTransaction
    op.drop_index("idx_payment_txn_customer", table_name="payment_transaction")
    op.drop_index("idx_payment_txn_created", table_name="payment_transaction")
    op.drop_index("idx_payment_txn_storefront", table_name="payment_transaction")
    op.drop_index("idx_payment_txn_tenant", table_name="payment_transaction")
    op.drop_index("idx_payment_txn_status", table_name="payment_transaction")
    op.drop_index("idx_payment_txn_intent_id", table_name="payment_transaction")
    op.drop_index("idx_payment_txn_provider_id", table_name="payment_transaction")
    op.drop_index("idx_payment_txn_order", table_name="payment_transaction")
    op.drop_table("payment_transaction")

    # Drop StorefrontPaymentMethod
    op.drop_index(
        "idx_storefront_method_enabled", table_name="storefront_payment_method"
    )
    op.drop_index(
        "idx_storefront_method_tenant", table_name="storefront_payment_method"
    )
    op.drop_index(
        "idx_storefront_method_storefront", table_name="storefront_payment_method"
    )
    op.drop_table("storefront_payment_method")

    # Drop TenantPaymentProvider
    op.drop_index(
        "idx_tenant_provider_enabled", table_name="tenant_payment_provider"
    )
    op.drop_index("idx_tenant_provider_tenant", table_name="tenant_payment_provider")
    op.drop_table("tenant_payment_provider")
