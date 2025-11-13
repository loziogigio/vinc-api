"""Base payment provider abstract class.

All payment providers must inherit from BasePaymentProvider and implement
the required abstract methods. This ensures a consistent interface across
all payment providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PaymentIntentResult:
    """Result from creating a payment intent.

    Attributes:
        payment_intent_id: Provider's payment intent ID
        client_secret: Client secret for completing payment (if applicable)
        redirect_url: URL to redirect customer to (if applicable)
        requires_action: Whether additional customer action is required
        status: Current status of the payment intent
        amount: Payment amount
        currency: Payment currency
        metadata: Additional metadata from provider
    """

    payment_intent_id: str
    client_secret: str | None = None
    redirect_url: str | None = None
    requires_action: bool = False
    status: str = "pending"
    amount: float = 0.0
    currency: str = "EUR"
    metadata: dict[str, Any] | None = None


@dataclass
class RefundResult:
    """Result from processing a refund.

    Attributes:
        refund_id: Provider's refund ID
        amount: Amount refunded
        currency: Currency of refund
        status: Refund status
        metadata: Additional metadata from provider
    """

    refund_id: str
    amount: float
    currency: str
    status: str
    metadata: dict[str, Any] | None = None


class BasePaymentProvider(ABC):
    """Abstract base class for payment providers.

    All payment providers must implement this interface to ensure
    consistency across different payment processors.
    """

    def __init__(self, credentials: dict[str, Any], mode: str = "test", config: dict[str, Any] | None = None):
        """Initialize the payment provider.

        Args:
            credentials: Provider credentials (API keys, secrets, etc.)
            mode: "test" or "live" mode
            config: Additional provider-specific configuration
        """
        self.credentials = credentials
        self.mode = mode
        self.config = config or {}

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'stripe', 'paypal')."""
        pass

    @abstractmethod
    async def create_payment_intent(
        self,
        amount: float,
        currency: str,
        order_id: str,
        customer_email: str,
        metadata: dict[str, Any] | None = None,
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> PaymentIntentResult:
        """Create a payment intent/session.

        Args:
            amount: Payment amount
            currency: Currency code (e.g., 'EUR', 'USD')
            order_id: Internal order ID for reference
            customer_email: Customer's email address
            metadata: Additional metadata to store with payment
            return_url: URL to return to after successful payment
            cancel_url: URL to return to if payment is cancelled

        Returns:
            PaymentIntentResult with payment details

        Raises:
            Exception: If payment intent creation fails
        """
        pass

    @abstractmethod
    async def confirm_payment(
        self,
        payment_intent_id: str,
        payment_data: dict[str, Any] | None = None,
    ) -> PaymentIntentResult:
        """Confirm a payment intent (for 3DS, additional auth, etc.).

        Args:
            payment_intent_id: Provider's payment intent ID
            payment_data: Additional payment data required for confirmation

        Returns:
            Updated PaymentIntentResult

        Raises:
            Exception: If confirmation fails
        """
        pass

    @abstractmethod
    async def get_payment_status(
        self,
        payment_intent_id: str,
    ) -> PaymentIntentResult:
        """Get the current status of a payment.

        Args:
            payment_intent_id: Provider's payment intent ID

        Returns:
            PaymentIntentResult with current status

        Raises:
            Exception: If status check fails
        """
        pass

    @abstractmethod
    async def refund_payment(
        self,
        transaction_id: str,
        amount: float | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Refund a payment.

        Args:
            transaction_id: Provider's transaction/charge ID
            amount: Amount to refund (None = full refund)
            reason: Reason for refund

        Returns:
            RefundResult with refund details

        Raises:
            Exception: If refund fails
        """
        pass

    @abstractmethod
    async def verify_webhook(
        self,
        payload: bytes | dict[str, Any],
        signature: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify and parse a webhook payload.

        Args:
            payload: Raw webhook payload
            signature: Webhook signature for verification
            headers: HTTP headers from webhook request

        Returns:
            Parsed and verified webhook event data

        Raises:
            Exception: If webhook verification fails
        """
        pass

    @abstractmethod
    def get_payment_method_info(self) -> dict[str, Any]:
        """Get information about this payment method for display.

        Returns:
            Dictionary with payment method information:
            - name: Provider name
            - display_name: Display name for customers
            - type: Payment method type (card, bank_transfer, etc.)
            - supports_refund: Whether refunds are supported
            - requires_redirect: Whether payment requires redirect
            - logo_url: URL to provider logo (optional)
            - min_amount: Minimum amount (optional)
            - max_amount: Maximum amount (optional)
        """
        pass

    def is_test_mode(self) -> bool:
        """Check if provider is in test mode.

        Returns:
            True if in test mode, False if in live mode
        """
        return self.mode == "test"

    def get_credential(self, key: str, default: Any = None) -> Any:
        """Safely get a credential value.

        Args:
            key: Credential key
            default: Default value if key not found

        Returns:
            Credential value or default
        """
        return self.credentials.get(key, default)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Safely get a configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)
