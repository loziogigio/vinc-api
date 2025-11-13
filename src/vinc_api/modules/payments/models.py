"""Payment database models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as UUIDType, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db_base import Base

# Valid provider values
PROVIDER_VALUES = (
    "stripe",
    "paypal",
    "nexi",
    "banca_sella",
    "scalapay",
    "bank_transfer",
)

# Valid status values for transactions
TRANSACTION_STATUS_VALUES = (
    "pending",
    "processing",
    "requires_action",
    "succeeded",
    "failed",
    "cancelled",
    "refunded",
    "partially_refunded",
)

# Valid mode values
MODE_VALUES = ("test", "live")

# Valid fee bearer values
FEE_BEARER_VALUES = ("wholesaler", "retailer", "customer", "split")


class TenantPaymentProvider(Base):
    """Payment providers configured and enabled by wholesalers (tenants).

    Each wholesaler can configure multiple payment providers with their own
    credentials and settings. This is the first level of payment configuration.
    """

    __tablename__ = "tenant_payment_provider"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_provider"),
        CheckConstraint(
            f"provider IN {PROVIDER_VALUES}",
            name="provider_valid",
        ),
        CheckConstraint(
            f"mode IN {MODE_VALUES}",
            name="mode_valid",
        ),
        CheckConstraint(
            f"fee_bearer IN {FEE_BEARER_VALUES}",
            name="fee_bearer_valid",
        ),
        Index("idx_tenant_provider_tenant", "tenant_id"),
        Index("idx_tenant_provider_enabled", "is_enabled"),
    )

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    mode: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="test",
        server_default=text("'test'"),
    )
    credentials: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Encrypted credentials for the payment provider",
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default={},
        server_default=text("'{}'::json"),
        comment="Provider-specific configuration settings",
    )
    fee_bearer: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="wholesaler",
        server_default=text("'wholesaler'"),
        comment="Who bears the payment processing fees",
    )
    fees: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default={},
        server_default=text("'{}'::json"),
        comment="Fee configuration (percentage, fixed amounts, etc.)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class StorefrontPaymentMethod(Base):
    """Payment methods enabled by retailers for their storefronts.

    Retailers can selectively enable payment methods (from those configured
    by their wholesaler) and customize display settings and conditions.
    This is the second level of payment configuration.
    """

    __tablename__ = "storefront_payment_method"
    __table_args__ = (
        UniqueConstraint("storefront_id", "provider", name="uq_storefront_provider"),
        CheckConstraint(
            f"provider IN {PROVIDER_VALUES}",
            name="provider_valid",
        ),
        Index("idx_storefront_method_storefront", "storefront_id"),
        Index("idx_storefront_method_tenant", "tenant_id"),
        Index("idx_storefront_method_enabled", "is_enabled"),
    )

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    storefront_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Denormalized for efficient querying",
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    display_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Custom display name for this payment method",
    )
    display_description: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Custom description shown to customers",
    )
    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Sort order for displaying payment methods",
    )
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default={},
        server_default=text("'{}'::json"),
        comment="Conditions for showing this method (min/max cart amount, etc.)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PaymentTransaction(Base):
    """All payment transactions with complete audit trail.

    This is the critical table for tracking all payment activity including
    attempts, successes, failures, and refunds. Every payment interaction
    should create or update a transaction record.
    """

    __tablename__ = "payment_transaction"
    __table_args__ = (
        CheckConstraint(
            f"status IN {TRANSACTION_STATUS_VALUES}",
            name="status_valid",
        ),
        CheckConstraint(
            f"provider IN {PROVIDER_VALUES}",
            name="provider_valid",
        ),
        Index("idx_payment_txn_order", "order_id"),
        Index("idx_payment_txn_provider_id", "provider_transaction_id"),
        Index("idx_payment_txn_intent_id", "provider_payment_intent_id"),
        Index("idx_payment_txn_status", "status"),
        Index("idx_payment_txn_tenant", "tenant_id"),
        Index("idx_payment_txn_storefront", "storefront_id"),
        Index("idx_payment_txn_created", "created_at"),
        Index("idx_payment_txn_customer", "customer_id"),
    )

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    storefront_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    order_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Reference to the order being paid",
    )

    # Provider information
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Payment provider used (stripe, paypal, etc.)",
    )
    provider_transaction_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="External transaction ID from the provider",
    )
    provider_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Payment intent/session ID from the provider",
    )

    # Amount information
    amount: Mapped[float] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="Transaction amount",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EUR",
        server_default=text("'EUR'"),
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Current status of the transaction",
    )
    payment_method_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Type of payment method used (card, bank_transfer, bnpl, etc.)",
    )

    # Customer information
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Metadata and logs
    metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default={},
        server_default=text("'{}'::json"),
        comment="Additional metadata (IP, user agent, etc.)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if the transaction failed",
    )
    webhook_events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=[],
        server_default=text("'[]'::json"),
        comment="Array of webhook events received for this transaction",
    )

    # Refund tracking
    refunded_amount: Mapped[float] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Total amount refunded",
    )
    refund_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for refund if applicable",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the payment was completed (succeeded or failed)",
    )


class PaymentWebhookLog(Base):
    """Logs of all webhook events received from payment providers.

    Essential for debugging payment issues and maintaining compliance.
    Stores the complete webhook payload and processing results.
    """

    __tablename__ = "payment_webhook_log"
    __table_args__ = (
        CheckConstraint(
            f"provider IN {PROVIDER_VALUES}",
            name="provider_valid",
        ),
        CheckConstraint(
            "status IN ('success','failed','pending','duplicate')",
            name="status_valid",
        ),
        Index("idx_webhook_log_provider", "provider"),
        Index("idx_webhook_log_event_id", "event_id"),
        Index("idx_webhook_log_created", "created_at"),
        Index("idx_webhook_log_transaction", "transaction_id"),
        Index("idx_webhook_log_status", "status"),
    )

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Type of webhook event (e.g., payment_intent.succeeded)",
    )
    event_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="Provider's unique event ID for deduplication",
    )

    # Webhook data
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="Complete webhook payload",
    )
    signature: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Webhook signature for verification",
    )
    headers: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="HTTP headers from webhook request",
    )

    # Processing status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Processing status (success, failed, pending, duplicate)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if processing failed",
    )
    processing_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Time taken to process the webhook in milliseconds",
    )

    # Related transaction
    transaction_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Related payment transaction if found",
    )

    # Timestamps
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the webhook was processed",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
