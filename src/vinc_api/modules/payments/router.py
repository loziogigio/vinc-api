"""Payment API router."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ...api.deps import get_db, get_tenant_id, require_roles
from .schemas import (
    ConfigureProviderRequest,
    CreatePaymentIntentRequest,
    EnableStorefrontMethodRequest,
    PaymentAnalytics,
    PaymentIntentResponse,
    PaymentMethodInfo,
    PaymentProvider,
    PaymentStatus,
    PaymentStatusResponse,
    RefundPaymentRequest,
    RefundResponse,
    StorefrontPaymentMethodResponse,
    TenantPaymentProviderResponse,
    TransactionLogResponse,
    UpdateProviderRequest,
)
from .service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


# ==== PUBLIC ENDPOINTS (Storefront Checkout) ====


@router.get(
    "/storefronts/{storefront_id}/methods",
    response_model=list[PaymentMethodInfo],
    summary="Get available payment methods",
    description="Get payment methods available for a storefront at checkout",
)
async def get_available_payment_methods(
    storefront_id: UUID,
    amount: float,
    currency: str = "EUR",
    db: Session = Depends(get_db),
) -> list[PaymentMethodInfo]:
    """Get available payment methods for checkout.

    This endpoint is public and used by storefront during checkout
    to display available payment options to customers.

    Args:
        storefront_id: Storefront ID
        amount: Cart amount
        currency: Currency code
        db: Database session

    Returns:
        List of available payment methods
    """
    service = PaymentService(db)
    return await service.get_available_payment_methods(storefront_id, amount, currency)


@router.post(
    "/intent",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create payment intent",
    description="Create a payment intent to initiate payment",
)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    db: Session = Depends(get_db),
) -> PaymentIntentResponse:
    """Create a payment intent.

    This creates a payment intent with the chosen provider and returns
    the necessary information to complete the payment (client secret,
    redirect URL, etc.).

    Args:
        request: Payment intent request
        db: Database session

    Returns:
        Payment intent response with transaction ID and payment details
    """
    service = PaymentService(db)
    return await service.create_payment_intent(request)


@router.get(
    "/{transaction_id}/status",
    response_model=PaymentStatusResponse,
    summary="Get payment status",
    description="Get the current status of a payment transaction",
)
async def get_payment_status(
    transaction_id: UUID,
    db: Session = Depends(get_db),
) -> PaymentStatusResponse:
    """Get payment transaction status.

    Args:
        transaction_id: Transaction ID
        db: Database session

    Returns:
        Payment status details

    Raises:
        HTTPException: If transaction not found
    """
    service = PaymentService(db)
    try:
        return await service.get_payment_status(transaction_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ==== ADMIN ENDPOINTS (Wholesaler - VINC-OFFICE) ====


@router.get(
    "/tenants/{tenant_id}/providers",
    response_model=list[TenantPaymentProviderResponse],
    summary="Get tenant payment providers",
    description="Get all payment providers configured for a tenant (wholesaler)",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin"))],
)
async def get_tenant_payment_providers(
    tenant_id: UUID,
    db: Session = Depends(get_db),
) -> list[TenantPaymentProviderResponse]:
    """Get all payment providers configured for a tenant.

    Requires super_admin or supplier_admin role.

    Args:
        tenant_id: Tenant ID
        db: Database session

    Returns:
        List of configured payment providers
    """
    service = PaymentService(db)
    return await service.get_tenant_providers(tenant_id)


@router.post(
    "/tenants/{tenant_id}/providers",
    response_model=TenantPaymentProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Configure payment provider",
    description="Configure a payment provider for a tenant (wholesaler)",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin"))],
)
async def configure_payment_provider(
    tenant_id: UUID,
    request: ConfigureProviderRequest,
    db: Session = Depends(get_db),
) -> TenantPaymentProviderResponse:
    """Configure a payment provider for a tenant.

    Credentials will be encrypted before storage.
    Requires super_admin or supplier_admin role.

    Args:
        tenant_id: Tenant ID
        request: Provider configuration
        db: Database session

    Returns:
        Configured provider response
    """
    service = PaymentService(db)
    return await service.configure_provider(tenant_id, request)


@router.patch(
    "/tenants/{tenant_id}/providers/{provider_id}",
    response_model=TenantPaymentProviderResponse,
    summary="Update payment provider",
    description="Update payment provider configuration",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin"))],
)
async def update_payment_provider(
    tenant_id: UUID,
    provider_id: UUID,
    request: UpdateProviderRequest,
    db: Session = Depends(get_db),
) -> TenantPaymentProviderResponse:
    """Update payment provider configuration.

    Requires super_admin or supplier_admin role.

    Args:
        tenant_id: Tenant ID (for validation)
        provider_id: Provider ID
        request: Update request
        db: Database session

    Returns:
        Updated provider response

    Raises:
        HTTPException: If provider not found
    """
    service = PaymentService(db)
    try:
        return await service.update_provider(provider_id, request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.delete(
    "/tenants/{tenant_id}/providers/{provider_id}",
    summary="Delete payment provider",
    description="Disable a payment provider for a tenant",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin"))],
)
async def delete_payment_provider(
    tenant_id: UUID,
    provider_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Disable a payment provider.

    This performs a soft delete by disabling the provider.
    Requires super_admin or supplier_admin role.

    Args:
        tenant_id: Tenant ID (for validation)
        provider_id: Provider ID
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If provider not found
    """
    service = PaymentService(db)
    try:
        return await service.delete_provider(provider_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ==== ADMIN ENDPOINTS (Retailer - VINC-STOREFRONT) ====


@router.get(
    "/storefronts/{storefront_id}/methods/config",
    response_model=list[StorefrontPaymentMethodResponse],
    summary="Get storefront payment configuration",
    description="Get payment methods configured for a storefront",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin", "reseller"))],
)
async def get_storefront_payment_config(
    storefront_id: UUID,
    db: Session = Depends(get_db),
) -> list[StorefrontPaymentMethodResponse]:
    """Get storefront's payment method configuration.

    Args:
        storefront_id: Storefront ID
        db: Database session

    Returns:
        List of configured payment methods
    """
    service = PaymentService(db)
    return await service.get_storefront_config(storefront_id)


@router.post(
    "/storefronts/{storefront_id}/methods",
    response_model=StorefrontPaymentMethodResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enable storefront payment method",
    description="Enable/configure a payment method for a storefront",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin", "reseller"))],
)
async def enable_storefront_payment_method(
    storefront_id: UUID,
    request: EnableStorefrontMethodRequest,
    request_obj: Request = None,  # type: ignore
    db: Session = Depends(get_db),
    tenant_id: Annotated[str | None, Depends(get_tenant_id)] = None,
) -> StorefrontPaymentMethodResponse:
    """Enable/configure a payment method for a storefront.

    The payment provider must be enabled at the tenant level first.

    Args:
        storefront_id: Storefront ID
        request: Method configuration
        request_obj: FastAPI request object
        db: Database session
        tenant_id: Tenant ID from header

    Returns:
        Configured method response

    Raises:
        HTTPException: If provider not enabled at tenant level
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID required",
        )

    service = PaymentService(db)
    try:
        return await service.enable_storefront_method(
            storefront_id=storefront_id,
            tenant_id=UUID(tenant_id),
            request=request,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


# ==== TRANSACTION MANAGEMENT ====


@router.get(
    "/transactions",
    response_model=list[TransactionLogResponse],
    summary="Get transaction logs",
    description="Get payment transaction logs with filters",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin"))],
)
async def get_transaction_logs(
    tenant_id: UUID | None = None,
    storefront_id: UUID | None = None,
    status_filter: PaymentStatus | None = None,
    provider: PaymentProvider | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[TransactionLogResponse]:
    """Get payment transaction logs with filters.

    Requires super_admin or supplier_admin role.

    Args:
        tenant_id: Filter by tenant
        storefront_id: Filter by storefront
        status_filter: Filter by status
        provider: Filter by provider
        start_date: Filter by start date
        end_date: Filter by end date
        limit: Results limit (default 100)
        offset: Results offset (default 0)
        db: Database session

    Returns:
        List of transaction logs
    """
    service = PaymentService(db)
    return await service.get_transaction_logs(
        tenant_id=tenant_id,
        storefront_id=storefront_id,
        status=status_filter,
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/transactions/{transaction_id}/refund",
    response_model=RefundResponse,
    summary="Refund payment",
    description="Refund a payment transaction",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin"))],
)
async def refund_payment(
    transaction_id: UUID,
    request: RefundPaymentRequest,
    db: Session = Depends(get_db),
) -> RefundResponse:
    """Refund a payment transaction.

    Requires super_admin or supplier_admin role.

    Args:
        transaction_id: Transaction ID
        request: Refund request (amount, reason)
        db: Database session

    Returns:
        Refund response

    Raises:
        HTTPException: If transaction not found or cannot be refunded
    """
    service = PaymentService(db)
    try:
        return await service.refund_payment(transaction_id, request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


# ==== ANALYTICS ====


@router.get(
    "/analytics",
    response_model=PaymentAnalytics,
    summary="Get payment analytics",
    description="Get payment analytics for a tenant",
    dependencies=[Depends(require_roles("super_admin", "supplier_admin", "wholesale_admin"))],
)
async def get_payment_analytics(
    tenant_id: UUID,
    start_date: datetime,
    end_date: datetime,
    db: Session = Depends(get_db),
) -> PaymentAnalytics:
    """Get payment analytics for a tenant.

    Provides statistics on transactions, amounts, success rates, etc.
    Requires super_admin or supplier_admin role.

    Args:
        tenant_id: Tenant ID
        start_date: Start date for analytics period
        end_date: End date for analytics period
        db: Database session

    Returns:
        Payment analytics data
    """
    service = PaymentService(db)
    return await service.get_analytics(tenant_id, start_date, end_date)


# ==== WEBHOOK ENDPOINTS ====
# Note: Webhooks are typically handled separately without authentication


@router.post(
    "/webhooks/stripe",
    summary="Stripe webhook",
    description="Handle Stripe webhook events",
    include_in_schema=False,  # Don't show in OpenAPI docs
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Handle Stripe webhooks.

    Args:
        request: FastAPI request
        stripe_signature: Stripe signature header
        db: Database session

    Returns:
        Success response
    """
    from .webhooks.stripe import StripeWebhookHandler

    body = await request.body()
    handler = StripeWebhookHandler(db)
    return await handler.handle(body, stripe_signature)


@router.post(
    "/webhooks/paypal",
    summary="PayPal webhook",
    description="Handle PayPal webhook events",
    include_in_schema=False,  # Don't show in OpenAPI docs
)
async def paypal_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Handle PayPal webhooks.

    Args:
        request: FastAPI request
        db: Database session

    Returns:
        Success response
    """
    from .webhooks.paypal import PayPalWebhookHandler

    body = await request.json()
    headers = dict(request.headers)
    handler = PayPalWebhookHandler(db)
    return await handler.handle(body, headers)


@router.post(
    "/webhooks/nexi",
    summary="Nexi webhook",
    description="Handle Nexi webhook events",
    include_in_schema=False,  # Don't show in OpenAPI docs
)
async def nexi_webhook(
    request: Request,
    nexi_signature: str = Header(None, alias="X-Nexi-Signature"),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Handle Nexi webhooks.

    Args:
        request: FastAPI request
        nexi_signature: Nexi MAC signature header
        db: Database session

    Returns:
        Success response
    """
    from .webhooks.nexi import NexiWebhookHandler

    body = await request.body()
    headers = dict(request.headers)
    handler = NexiWebhookHandler(db)
    return await handler.handle(body, nexi_signature, headers)
