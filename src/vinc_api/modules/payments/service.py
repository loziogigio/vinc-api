"""Payment service layer with business logic."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .models import (
    PaymentTransaction,
    PaymentWebhookLog,
    StorefrontPaymentMethod,
    TenantPaymentProvider,
)
from .providers import BasePaymentProvider, PayPalProvider, StripeProvider
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
from .utils.encryption import get_encryption_handler


class PaymentService:
    """Service layer for payment operations."""

    def __init__(self, db: Session):
        """Initialize payment service.

        Args:
            db: Database session
        """
        self.db = db
        self.encryption = get_encryption_handler()

    # === Provider Management (Tenant Level) ===

    async def get_tenant_providers(
        self, tenant_id: UUID
    ) -> list[TenantPaymentProviderResponse]:
        """Get all payment providers configured for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of configured payment providers
        """
        stmt = select(TenantPaymentProvider).where(
            TenantPaymentProvider.tenant_id == tenant_id
        )
        result = self.db.execute(stmt)
        providers = result.scalars().all()

        return [
            TenantPaymentProviderResponse(
                id=p.id,
                provider=PaymentProvider(p.provider),
                is_enabled=p.is_enabled,
                mode=p.mode,  # type: ignore
                has_credentials=bool(p.credentials),
                fee_bearer=p.fee_bearer,  # type: ignore
                config=p.config,
                fees=p.fees,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in providers
        ]

    async def configure_provider(
        self, tenant_id: UUID, request: ConfigureProviderRequest
    ) -> TenantPaymentProviderResponse:
        """Configure a payment provider for a tenant.

        Args:
            tenant_id: Tenant ID
            request: Provider configuration request

        Returns:
            Configured provider response
        """
        # Encrypt credentials
        encrypted_creds = self.encryption.encrypt(request.credentials)

        # Check if provider already exists
        stmt = select(TenantPaymentProvider).where(
            and_(
                TenantPaymentProvider.tenant_id == tenant_id,
                TenantPaymentProvider.provider == request.provider.value,
            )
        )
        existing = self.db.execute(stmt).scalar_one_or_none()

        if existing:
            # Update existing
            existing.credentials = encrypted_creds
            existing.mode = request.mode.value
            existing.config = request.config
            existing.fee_bearer = request.fee_bearer.value
            existing.fees = request.fees
            existing.is_enabled = True
            existing.updated_at = datetime.utcnow()
            provider = existing
        else:
            # Create new
            provider = TenantPaymentProvider(
                tenant_id=tenant_id,
                provider=request.provider.value,
                credentials=encrypted_creds,
                mode=request.mode.value,
                config=request.config,
                fee_bearer=request.fee_bearer.value,
                fees=request.fees,
                is_enabled=True,
            )
            self.db.add(provider)

        self.db.commit()
        self.db.refresh(provider)

        return TenantPaymentProviderResponse(
            id=provider.id,
            provider=PaymentProvider(provider.provider),
            is_enabled=provider.is_enabled,
            mode=provider.mode,  # type: ignore
            has_credentials=bool(provider.credentials),
            fee_bearer=provider.fee_bearer,  # type: ignore
            config=provider.config,
            fees=provider.fees,
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )

    async def update_provider(
        self, provider_id: UUID, updates: UpdateProviderRequest
    ) -> TenantPaymentProviderResponse:
        """Update payment provider configuration.

        Args:
            provider_id: Provider ID
            updates: Update request

        Returns:
            Updated provider response

        Raises:
            ValueError: If provider not found
        """
        stmt = select(TenantPaymentProvider).where(TenantPaymentProvider.id == provider_id)
        provider = self.db.execute(stmt).scalar_one_or_none()

        if not provider:
            raise ValueError(f"Provider {provider_id} not found")

        # Update fields
        if updates.is_enabled is not None:
            provider.is_enabled = updates.is_enabled
        if updates.credentials is not None:
            provider.credentials = self.encryption.encrypt(updates.credentials)
        if updates.mode is not None:
            provider.mode = updates.mode.value
        if updates.config is not None:
            provider.config = updates.config
        if updates.fee_bearer is not None:
            provider.fee_bearer = updates.fee_bearer.value
        if updates.fees is not None:
            provider.fees = updates.fees

        provider.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(provider)

        return TenantPaymentProviderResponse(
            id=provider.id,
            provider=PaymentProvider(provider.provider),
            is_enabled=provider.is_enabled,
            mode=provider.mode,  # type: ignore
            has_credentials=bool(provider.credentials),
            fee_bearer=provider.fee_bearer,  # type: ignore
            config=provider.config,
            fees=provider.fees,
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )

    async def delete_provider(self, provider_id: UUID) -> dict[str, str]:
        """Delete/disable a payment provider.

        Args:
            provider_id: Provider ID

        Returns:
            Success message

        Raises:
            ValueError: If provider not found
        """
        stmt = select(TenantPaymentProvider).where(TenantPaymentProvider.id == provider_id)
        provider = self.db.execute(stmt).scalar_one_or_none()

        if not provider:
            raise ValueError(f"Provider {provider_id} not found")

        # Soft delete by disabling
        provider.is_enabled = False
        provider.updated_at = datetime.utcnow()
        self.db.commit()

        return {"message": "Provider disabled successfully"}

    # === Storefront Payment Methods (Retailer Level) ===

    async def get_storefront_config(
        self, storefront_id: UUID
    ) -> list[StorefrontPaymentMethodResponse]:
        """Get storefront's payment method configuration.

        Args:
            storefront_id: Storefront ID

        Returns:
            List of configured payment methods
        """
        stmt = select(StorefrontPaymentMethod).where(
            StorefrontPaymentMethod.storefront_id == storefront_id
        )
        result = self.db.execute(stmt)
        methods = result.scalars().all()

        return [
            StorefrontPaymentMethodResponse(
                id=m.id,
                storefront_id=m.storefront_id,
                provider=PaymentProvider(m.provider),
                is_enabled=m.is_enabled,
                display_name=m.display_name,
                display_description=m.display_description,
                display_order=m.display_order,
                conditions=m.conditions,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in methods
        ]

    async def enable_storefront_method(
        self,
        storefront_id: UUID,
        tenant_id: UUID,
        request: EnableStorefrontMethodRequest,
    ) -> StorefrontPaymentMethodResponse:
        """Enable/configure a payment method for a storefront.

        Args:
            storefront_id: Storefront ID
            tenant_id: Tenant ID (for validation)
            request: Method configuration request

        Returns:
            Configured method response

        Raises:
            ValueError: If provider not enabled at tenant level
        """
        # Verify provider is enabled at tenant level
        stmt = select(TenantPaymentProvider).where(
            and_(
                TenantPaymentProvider.tenant_id == tenant_id,
                TenantPaymentProvider.provider == request.provider.value,
                TenantPaymentProvider.is_enabled == True,  # noqa: E712
            )
        )
        tenant_provider = self.db.execute(stmt).scalar_one_or_none()

        if not tenant_provider:
            raise ValueError(
                f"Provider {request.provider.value} not enabled for this tenant"
            )

        # Check if method already exists
        stmt = select(StorefrontPaymentMethod).where(
            and_(
                StorefrontPaymentMethod.storefront_id == storefront_id,
                StorefrontPaymentMethod.provider == request.provider.value,
            )
        )
        existing = self.db.execute(stmt).scalar_one_or_none()

        if existing:
            # Update existing
            existing.is_enabled = request.is_enabled
            existing.display_name = request.display_name
            existing.display_description = request.display_description
            existing.display_order = request.display_order
            existing.conditions = request.conditions
            existing.updated_at = datetime.utcnow()
            method = existing
        else:
            # Create new
            method = StorefrontPaymentMethod(
                storefront_id=storefront_id,
                tenant_id=tenant_id,
                provider=request.provider.value,
                is_enabled=request.is_enabled,
                display_name=request.display_name,
                display_description=request.display_description,
                display_order=request.display_order,
                conditions=request.conditions,
            )
            self.db.add(method)

        self.db.commit()
        self.db.refresh(method)

        return StorefrontPaymentMethodResponse(
            id=method.id,
            storefront_id=method.storefront_id,
            provider=PaymentProvider(method.provider),
            is_enabled=method.is_enabled,
            display_name=method.display_name,
            display_description=method.display_description,
            display_order=method.display_order,
            conditions=method.conditions,
            created_at=method.created_at,
            updated_at=method.updated_at,
        )

    # === Payment Method Discovery (Public) ===

    async def get_available_payment_methods(
        self, storefront_id: UUID, amount: float, currency: str
    ) -> list[PaymentMethodInfo]:
        """Get available payment methods for a storefront at checkout.

        Args:
            storefront_id: Storefront ID
            amount: Cart amount
            currency: Currency code

        Returns:
            List of available payment methods with display info
        """
        # Get storefront methods (with tenant)
        stmt = (
            select(StorefrontPaymentMethod, TenantPaymentProvider)
            .join(
                TenantPaymentProvider,
                and_(
                    TenantPaymentProvider.tenant_id == StorefrontPaymentMethod.tenant_id,
                    TenantPaymentProvider.provider == StorefrontPaymentMethod.provider,
                ),
            )
            .where(
                and_(
                    StorefrontPaymentMethod.storefront_id == storefront_id,
                    StorefrontPaymentMethod.is_enabled == True,  # noqa: E712
                    TenantPaymentProvider.is_enabled == True,  # noqa: E712
                )
            )
        )

        result = self.db.execute(stmt)
        methods = result.all()

        available: list[PaymentMethodInfo] = []

        for storefront_method, tenant_provider in methods:
            # Check conditions
            conditions = storefront_method.conditions or {}
            min_amount = conditions.get("min_cart")
            max_amount = conditions.get("max_cart")

            if min_amount and amount < min_amount:
                continue
            if max_amount and amount > max_amount:
                continue

            # Get provider instance for info
            provider = self._get_provider_instance(tenant_provider)
            info = provider.get_payment_method_info()

            # Create method info
            method_info = PaymentMethodInfo(
                provider=PaymentProvider(storefront_method.provider),
                name=info["name"],
                display_name=storefront_method.display_name or info["display_name"],
                display_description=storefront_method.display_description,
                logo_url=info.get("logo_url"),
                type=info["type"],  # type: ignore
                min_amount=min_amount or info.get("min_amount"),
                max_amount=max_amount or info.get("max_amount"),
                supports_refund=info["supports_refund"],
                requires_redirect=info["requires_redirect"],
                display_order=storefront_method.display_order,
            )
            available.append(method_info)

        # Sort by display_order
        available.sort(key=lambda m: m.display_order)

        return available

    # === Payment Processing ===

    async def create_payment_intent(
        self, request: CreatePaymentIntentRequest
    ) -> PaymentIntentResponse:
        """Create a payment intent.

        Args:
            request: Payment intent request

        Returns:
            Payment intent response with transaction ID

        Raises:
            ValueError: If provider not available or configured
        """
        # Get tenant provider
        stmt = (
            select(StorefrontPaymentMethod, TenantPaymentProvider)
            .join(
                TenantPaymentProvider,
                and_(
                    TenantPaymentProvider.tenant_id == StorefrontPaymentMethod.tenant_id,
                    TenantPaymentProvider.provider == StorefrontPaymentMethod.provider,
                ),
            )
            .where(
                and_(
                    StorefrontPaymentMethod.storefront_id == request.storefront_id,
                    StorefrontPaymentMethod.provider == request.provider.value,
                    StorefrontPaymentMethod.is_enabled == True,  # noqa: E712
                    TenantPaymentProvider.is_enabled == True,  # noqa: E712
                )
            )
        )

        result = self.db.execute(stmt).first()
        if not result:
            raise ValueError(
                f"Payment provider {request.provider.value} not available for this storefront"
            )

        storefront_method, tenant_provider = result

        # Create transaction record
        transaction = PaymentTransaction(
            tenant_id=tenant_provider.tenant_id,
            storefront_id=request.storefront_id,
            order_id=request.order_id,
            provider=request.provider.value,
            amount=request.amount,
            currency=request.currency,
            status=PaymentStatus.PENDING.value,
            customer_email=request.customer_email,
            customer_id=request.customer_id,
            metadata=request.metadata,
        )
        self.db.add(transaction)
        self.db.flush()  # Get transaction ID

        try:
            # Get provider instance
            provider = self._get_provider_instance(tenant_provider)

            # Create payment intent
            intent_result = await provider.create_payment_intent(
                amount=request.amount,
                currency=request.currency,
                order_id=str(request.order_id),
                customer_email=request.customer_email,
                metadata=request.metadata,
                return_url=request.return_url,
                cancel_url=request.cancel_url,
            )

            # Update transaction with provider details
            transaction.provider_payment_intent_id = intent_result.payment_intent_id
            transaction.status = intent_result.status
            transaction.metadata.update(intent_result.metadata or {})

            self.db.commit()
            self.db.refresh(transaction)

            return PaymentIntentResponse(
                payment_intent_id=intent_result.payment_intent_id,
                transaction_id=transaction.id,
                client_secret=intent_result.client_secret,
                redirect_url=intent_result.redirect_url,
                requires_action=intent_result.requires_action,
                status=PaymentStatus(intent_result.status),
                amount=request.amount,
                currency=request.currency,
            )

        except Exception as e:
            # Update transaction with error
            transaction.status = PaymentStatus.FAILED.value
            transaction.error_message = str(e)
            self.db.commit()
            raise

    async def get_payment_status(
        self, transaction_id: UUID
    ) -> PaymentStatusResponse:
        """Get payment transaction status.

        Args:
            transaction_id: Transaction ID

        Returns:
            Payment status response

        Raises:
            ValueError: If transaction not found
        """
        stmt = select(PaymentTransaction).where(PaymentTransaction.id == transaction_id)
        transaction = self.db.execute(stmt).scalar_one_or_none()

        if not transaction:
            raise ValueError(f"Transaction {transaction_id} not found")

        return PaymentStatusResponse.model_validate(transaction)

    async def refund_payment(
        self, transaction_id: UUID, request: RefundPaymentRequest
    ) -> RefundResponse:
        """Refund a payment transaction.

        Args:
            transaction_id: Transaction ID
            request: Refund request

        Returns:
            Refund response

        Raises:
            ValueError: If transaction not found or cannot be refunded
        """
        stmt = select(PaymentTransaction, TenantPaymentProvider).join(
            TenantPaymentProvider,
            and_(
                TenantPaymentProvider.tenant_id == PaymentTransaction.tenant_id,
                TenantPaymentProvider.provider == PaymentTransaction.provider,
            ),
        ).where(PaymentTransaction.id == transaction_id)

        result = self.db.execute(stmt).first()
        if not result:
            raise ValueError(f"Transaction {transaction_id} not found")

        transaction, tenant_provider = result

        if transaction.status != PaymentStatus.SUCCEEDED.value:
            raise ValueError("Only succeeded payments can be refunded")

        # Get provider instance
        provider = self._get_provider_instance(tenant_provider)

        # Process refund
        refund_result = await provider.refund_payment(
            transaction_id=transaction.provider_transaction_id or transaction.provider_payment_intent_id or "",
            amount=request.amount,
            reason=request.reason,
        )

        # Update transaction
        refund_amount = request.amount or transaction.amount
        transaction.refunded_amount = float(transaction.refunded_amount) + refund_amount
        transaction.refund_reason = request.reason

        if transaction.refunded_amount >= transaction.amount:
            transaction.status = PaymentStatus.REFUNDED.value
        else:
            transaction.status = PaymentStatus.PARTIALLY_REFUNDED.value

        self.db.commit()

        return RefundResponse(
            transaction_id=transaction.id,
            refund_id=refund_result.refund_id,
            amount=refund_result.amount,
            currency=refund_result.currency,
            status=refund_result.status,
            created_at=datetime.utcnow(),
        )

    # === Transaction Logs & Analytics ===

    async def get_transaction_logs(
        self,
        tenant_id: UUID | None = None,
        storefront_id: UUID | None = None,
        status: PaymentStatus | None = None,
        provider: PaymentProvider | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TransactionLogResponse]:
        """Get payment transaction logs with filters.

        Args:
            tenant_id: Filter by tenant
            storefront_id: Filter by storefront
            status: Filter by status
            provider: Filter by provider
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Results limit
            offset: Results offset

        Returns:
            List of transaction logs
        """
        stmt = select(PaymentTransaction)

        # Apply filters
        if tenant_id:
            stmt = stmt.where(PaymentTransaction.tenant_id == tenant_id)
        if storefront_id:
            stmt = stmt.where(PaymentTransaction.storefront_id == storefront_id)
        if status:
            stmt = stmt.where(PaymentTransaction.status == status.value)
        if provider:
            stmt = stmt.where(PaymentTransaction.provider == provider.value)
        if start_date:
            stmt = stmt.where(PaymentTransaction.created_at >= start_date)
        if end_date:
            stmt = stmt.where(PaymentTransaction.created_at <= end_date)

        # Order and paginate
        stmt = stmt.order_by(PaymentTransaction.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = self.db.execute(stmt)
        transactions = result.scalars().all()

        return [TransactionLogResponse.model_validate(t) for t in transactions]

    async def get_analytics(
        self, tenant_id: UUID, start_date: datetime, end_date: datetime
    ) -> PaymentAnalytics:
        """Get payment analytics for a tenant.

        Args:
            tenant_id: Tenant ID
            start_date: Start date
            end_date: End date

        Returns:
            Payment analytics
        """
        stmt = select(PaymentTransaction).where(
            and_(
                PaymentTransaction.tenant_id == tenant_id,
                PaymentTransaction.created_at >= start_date,
                PaymentTransaction.created_at <= end_date,
            )
        )

        result = self.db.execute(stmt)
        transactions = result.scalars().all()

        # Calculate analytics
        total_transactions = len(transactions)
        total_amount = sum(float(t.amount) for t in transactions)
        successful_transactions = sum(
            1 for t in transactions if t.status == PaymentStatus.SUCCEEDED.value
        )
        successful_amount = sum(
            float(t.amount)
            for t in transactions
            if t.status == PaymentStatus.SUCCEEDED.value
        )
        failed_transactions = sum(
            1 for t in transactions if t.status == PaymentStatus.FAILED.value
        )
        refunded_transactions = sum(
            1
            for t in transactions
            if t.status
            in [
                PaymentStatus.REFUNDED.value,
                PaymentStatus.PARTIALLY_REFUNDED.value,
            ]
        )
        refunded_amount = sum(float(t.refunded_amount) for t in transactions)

        # By provider
        by_provider: dict[str, dict[str, Any]] = {}
        for t in transactions:
            if t.provider not in by_provider:
                by_provider[t.provider] = {
                    "count": 0,
                    "amount": 0.0,
                    "successful": 0,
                }
            by_provider[t.provider]["count"] += 1
            by_provider[t.provider]["amount"] += float(t.amount)
            if t.status == PaymentStatus.SUCCEEDED.value:
                by_provider[t.provider]["successful"] += 1

        # By status
        by_status: dict[str, int] = {}
        for t in transactions:
            by_status[t.status] = by_status.get(t.status, 0) + 1

        return PaymentAnalytics(
            total_transactions=total_transactions,
            total_amount=total_amount,
            successful_transactions=successful_transactions,
            successful_amount=successful_amount,
            failed_transactions=failed_transactions,
            refunded_transactions=refunded_transactions,
            refunded_amount=refunded_amount,
            by_provider=by_provider,
            by_status=by_status,
        )

    # === Helper Methods ===

    def _get_provider_instance(
        self, tenant_provider: TenantPaymentProvider
    ) -> BasePaymentProvider:
        """Get payment provider instance.

        Args:
            tenant_provider: Tenant payment provider model

        Returns:
            Payment provider instance

        Raises:
            ValueError: If provider not supported
        """
        # Decrypt credentials
        credentials = self.encryption.decrypt(tenant_provider.credentials)

        # Get provider class
        from .providers import (
            BancaSellaProvider,
            BankTransferProvider,
            NexiProvider,
            ScalapayProvider,
        )

        provider_map = {
            "stripe": StripeProvider,
            "paypal": PayPalProvider,
            "nexi": NexiProvider,
            "banca_sella": BancaSellaProvider,
            "scalapay": ScalapayProvider,
            "bank_transfer": BankTransferProvider,
        }

        provider_class = provider_map.get(tenant_provider.provider)
        if not provider_class:
            raise ValueError(f"Provider {tenant_provider.provider} not supported")

        return provider_class(
            credentials=credentials,
            mode=tenant_provider.mode,
            config=tenant_provider.config,
        )
