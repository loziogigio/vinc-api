"""Payment Pydantic schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

try:
    from pydantic import BaseModel, ConfigDict, Field, field_validator
except Exception:  # pragma: no cover

    class BaseModel:  # type: ignore
        pass

    def Field(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        return None

    class ConfigDict(dict):  # type: ignore
        pass

    def field_validator(*args: Any, **kwargs: Any) -> Any:  # type: ignore
        def decorator(func: Any) -> Any:
            return func

        return decorator


# Enums
class PaymentProvider(str, Enum):
    """Supported payment providers."""

    STRIPE = "stripe"
    PAYPAL = "paypal"
    NEXI = "nexi"
    BANCA_SELLA = "banca_sella"
    SCALAPAY = "scalapay"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(str, Enum):
    """Payment transaction statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    REQUIRES_ACTION = "requires_action"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMode(str, Enum):
    """Payment provider mode."""

    TEST = "test"
    LIVE = "live"


class FeeBearer(str, Enum):
    """Who bears the payment processing fees."""

    WHOLESALER = "wholesaler"
    RETAILER = "retailer"
    CUSTOMER = "customer"
    SPLIT = "split"


class PaymentMethodType(str, Enum):
    """Types of payment methods."""

    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    BNPL = "bnpl"  # Buy Now Pay Later
    DIGITAL_WALLET = "digital_wallet"


class PaymentType(str, Enum):
    """Types of payment transactions."""

    STANDARD = "standard"  # Standard one-time payment
    RECURRENT = "recurrent"  # Recurring/subscription payment
    MOTO = "moto"  # Mail Order/Telephone Order
    ONE_CLICK = "one_click"  # One-click payment with saved card


# Request Schemas


class ConfigureProviderRequest(BaseModel):
    """Request to configure a payment provider for a tenant."""

    provider: PaymentProvider
    credentials: dict[str, Any] = Field(
        ...,
        description="Provider credentials (will be encrypted)",
    )
    mode: PaymentMode = Field(
        default=PaymentMode.TEST,
        description="Test or live mode",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific configuration",
    )
    fee_bearer: FeeBearer = Field(
        default=FeeBearer.WHOLESALER,
        description="Who bears payment fees",
    )
    fees: dict[str, Any] = Field(
        default_factory=dict,
        description="Fee configuration",
    )

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(use_enum_values=True)
    else:

        class Config:  # type: ignore
            use_enum_values = True


class UpdateProviderRequest(BaseModel):
    """Request to update a payment provider configuration."""

    is_enabled: bool | None = None
    credentials: dict[str, Any] | None = Field(
        default=None,
        description="Updated credentials (will be encrypted)",
    )
    mode: PaymentMode | None = None
    config: dict[str, Any] | None = None
    fee_bearer: FeeBearer | None = None
    fees: dict[str, Any] | None = None

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(use_enum_values=True)
    else:

        class Config:  # type: ignore
            use_enum_values = True


class EnableStorefrontMethodRequest(BaseModel):
    """Request to enable a payment method for a storefront."""

    provider: PaymentProvider
    is_enabled: bool = True
    display_name: str | None = Field(
        default=None,
        description="Custom display name",
    )
    display_description: str | None = Field(
        default=None,
        description="Custom description",
    )
    display_order: int = Field(
        default=0,
        description="Sort order",
    )
    conditions: dict[str, Any] = Field(
        default_factory=dict,
        description="Conditions (min/max cart amount, etc.)",
    )

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(use_enum_values=True)
    else:

        class Config:  # type: ignore
            use_enum_values = True


class CreatePaymentIntentRequest(BaseModel):
    """Request to create a payment intent."""

    storefront_id: UUID
    order_id: UUID
    provider: PaymentProvider
    amount: float = Field(..., gt=0, description="Payment amount")
    currency: str = Field(default="EUR", max_length=3)
    customer_email: str
    customer_id: UUID | None = None
    payment_type: PaymentType = Field(
        default=PaymentType.STANDARD,
        description="Type of payment (standard, recurrent, moto, one_click)",
    )
    saved_card_id: str | None = Field(
        default=None,
        description="Saved card ID for one-click payments",
    )
    save_card: bool = Field(
        default=False,
        description="Save card for future one-click payments",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )
    return_url: str | None = Field(
        default=None,
        description="URL to return to after payment",
    )
    cancel_url: str | None = Field(
        default=None,
        description="URL to return to if payment cancelled",
    )

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(use_enum_values=True)
    else:

        class Config:  # type: ignore
            use_enum_values = True


class ConfirmPaymentRequest(BaseModel):
    """Request to confirm a payment (for 3DS, etc.)."""

    payment_method_id: str | None = None
    payment_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional payment data",
    )


class RefundPaymentRequest(BaseModel):
    """Request to refund a payment."""

    amount: float | None = Field(
        default=None,
        gt=0,
        description="Amount to refund (None = full refund)",
    )
    reason: str | None = Field(
        default=None,
        description="Reason for refund",
    )


# Response Schemas


class PaymentMethodInfo(BaseModel):
    """Information about an available payment method."""

    provider: PaymentProvider
    name: str = Field(description="Provider name")
    display_name: str = Field(description="Display name for customers")
    display_description: str | None = Field(
        default=None,
        description="Description for customers",
    )
    logo_url: str | None = Field(
        default=None,
        description="Logo URL",
    )
    type: PaymentMethodType = Field(description="Payment method type")
    min_amount: float | None = Field(
        default=None,
        description="Minimum amount",
    )
    max_amount: float | None = Field(
        default=None,
        description="Maximum amount",
    )
    supports_refund: bool = Field(description="Whether refunds are supported")
    requires_redirect: bool = Field(
        description="Whether payment requires redirect"
    )
    display_order: int = Field(default=0, description="Sort order")

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(use_enum_values=True)
    else:

        class Config:  # type: ignore
            use_enum_values = True


class PaymentIntentResponse(BaseModel):
    """Response after creating a payment intent."""

    payment_intent_id: str = Field(description="Provider's payment intent ID")
    transaction_id: UUID = Field(description="Our internal transaction ID")
    client_secret: str | None = Field(
        default=None,
        description="Client secret for completing payment",
    )
    redirect_url: str | None = Field(
        default=None,
        description="URL to redirect customer to",
    )
    requires_action: bool = Field(
        description="Whether additional action is required"
    )
    status: PaymentStatus = Field(description="Payment status")
    amount: float
    currency: str

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(use_enum_values=True)
    else:

        class Config:  # type: ignore
            use_enum_values = True


class PaymentStatusResponse(BaseModel):
    """Response with payment status."""

    transaction_id: UUID
    status: PaymentStatus
    amount: float
    currency: str
    provider: PaymentProvider
    provider_transaction_id: str | None = None
    provider_payment_intent_id: str | None = None
    error_message: str | None = None
    payment_method_type: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    else:

        class Config:  # type: ignore
            from_attributes = True
            use_enum_values = True


class TenantPaymentProviderResponse(BaseModel):
    """Response with tenant payment provider configuration."""

    id: UUID
    provider: PaymentProvider
    is_enabled: bool
    mode: PaymentMode
    has_credentials: bool = Field(
        description="Whether credentials are configured (not exposed)"
    )
    fee_bearer: FeeBearer
    config: dict[str, Any] = Field(default_factory=dict)
    fees: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    else:

        class Config:  # type: ignore
            from_attributes = True
            use_enum_values = True


class StorefrontPaymentMethodResponse(BaseModel):
    """Response with storefront payment method configuration."""

    id: UUID
    storefront_id: UUID
    provider: PaymentProvider
    is_enabled: bool
    display_name: str | None
    display_description: str | None
    display_order: int
    conditions: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    else:

        class Config:  # type: ignore
            from_attributes = True
            use_enum_values = True


class TransactionLogResponse(BaseModel):
    """Response with transaction log details."""

    id: UUID
    tenant_id: UUID
    storefront_id: UUID | None
    order_id: UUID
    provider: PaymentProvider
    amount: float
    currency: str
    status: PaymentStatus
    payment_method_type: str | None
    customer_email: str | None
    customer_id: UUID | None
    refunded_amount: float
    refund_reason: str | None
    error_message: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    if hasattr(BaseModel, "model_config"):
        model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    else:

        class Config:  # type: ignore
            from_attributes = True
            use_enum_values = True


class RefundResponse(BaseModel):
    """Response after processing a refund."""

    transaction_id: UUID
    refund_id: str = Field(description="Provider's refund ID")
    amount: float = Field(description="Amount refunded")
    currency: str
    status: str = Field(description="Refund status")
    created_at: datetime


class PaymentAnalytics(BaseModel):
    """Payment analytics response."""

    total_transactions: int
    total_amount: float
    successful_transactions: int
    successful_amount: float
    failed_transactions: int
    refunded_transactions: int
    refunded_amount: float
    by_provider: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Breakdown by provider",
    )
    by_status: dict[str, int] = Field(
        default_factory=dict,
        description="Breakdown by status",
    )
