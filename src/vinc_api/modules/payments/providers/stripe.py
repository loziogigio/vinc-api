"""Stripe payment provider implementation."""

from typing import Any

from .base import BasePaymentProvider, PaymentIntentResult, RefundResult


class StripeProvider(BasePaymentProvider):
    """Stripe payment provider implementation.

    Supports card payments, various wallets (Apple Pay, Google Pay),
    and SEPA Direct Debit through Stripe's Payment Intents API.
    """

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "stripe"

    def _get_stripe(self) -> Any:
        """Get Stripe module and configure API key.

        Returns:
            Configured stripe module

        Raises:
            ImportError: If stripe module is not installed
        """
        try:
            import stripe
        except ImportError as e:
            raise ImportError(
                "Stripe library not installed. Install with: pip install stripe"
            ) from e

        # Configure API key
        api_key = self.get_credential("secret_key")
        if not api_key:
            raise ValueError("Stripe secret_key not configured in credentials")

        stripe.api_key = api_key
        return stripe

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
        """Create a Stripe Payment Intent.

        Args:
            amount: Payment amount in decimal (e.g., 10.50 for €10.50)
            currency: Currency code (e.g., 'eur')
            order_id: Internal order ID
            customer_email: Customer email
            metadata: Additional metadata
            return_url: Return URL after payment
            cancel_url: Cancel URL

        Returns:
            PaymentIntentResult with payment details
        """
        stripe = self._get_stripe()

        # Convert amount to cents (Stripe expects smallest currency unit)
        amount_cents = int(amount * 100)

        # Build metadata
        intent_metadata = {
            "order_id": order_id,
            "customer_email": customer_email,
        }
        if metadata:
            intent_metadata.update(metadata)

        # Payment method types to enable
        payment_method_types = self.get_config(
            "payment_method_types",
            ["card"],  # Default to card only
        )

        try:
            # Create Payment Intent
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency.lower(),
                payment_method_types=payment_method_types,
                receipt_email=customer_email,
                metadata=intent_metadata,
                automatic_payment_methods=self.get_config(
                    "automatic_payment_methods",
                    {"enabled": True},
                ),
            )

            return PaymentIntentResult(
                payment_intent_id=intent.id,
                client_secret=intent.client_secret,
                redirect_url=None,  # Stripe doesn't redirect for PaymentIntent
                requires_action=intent.status == "requires_action",
                status=self._map_stripe_status(intent.status),
                amount=amount,
                currency=currency,
                metadata={"stripe_intent": intent.to_dict()},
            )

        except stripe.error.StripeError as e:
            raise Exception(f"Stripe API error: {str(e)}") from e

    async def confirm_payment(
        self,
        payment_intent_id: str,
        payment_data: dict[str, Any] | None = None,
    ) -> PaymentIntentResult:
        """Confirm a Stripe Payment Intent.

        Args:
            payment_intent_id: Stripe payment intent ID
            payment_data: Additional payment data (payment_method_id, etc.)

        Returns:
            Updated PaymentIntentResult
        """
        stripe = self._get_stripe()
        payment_data = payment_data or {}

        try:
            # Confirm the payment intent
            intent = stripe.PaymentIntent.confirm(
                payment_intent_id,
                payment_method=payment_data.get("payment_method_id"),
                return_url=payment_data.get("return_url"),
            )

            return PaymentIntentResult(
                payment_intent_id=intent.id,
                client_secret=intent.client_secret,
                redirect_url=intent.next_action.redirect_to_url.url
                if intent.next_action and hasattr(intent.next_action, "redirect_to_url")
                else None,
                requires_action=intent.status == "requires_action",
                status=self._map_stripe_status(intent.status),
                amount=float(intent.amount / 100),
                currency=intent.currency.upper(),
                metadata={"stripe_intent": intent.to_dict()},
            )

        except stripe.error.StripeError as e:
            raise Exception(f"Stripe API error: {str(e)}") from e

    async def get_payment_status(
        self,
        payment_intent_id: str,
    ) -> PaymentIntentResult:
        """Get status of a Stripe Payment Intent.

        Args:
            payment_intent_id: Stripe payment intent ID

        Returns:
            PaymentIntentResult with current status
        """
        stripe = self._get_stripe()

        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            return PaymentIntentResult(
                payment_intent_id=intent.id,
                client_secret=intent.client_secret,
                redirect_url=intent.next_action.redirect_to_url.url
                if intent.next_action and hasattr(intent.next_action, "redirect_to_url")
                else None,
                requires_action=intent.status == "requires_action",
                status=self._map_stripe_status(intent.status),
                amount=float(intent.amount / 100),
                currency=intent.currency.upper(),
                metadata={"stripe_intent": intent.to_dict()},
            )

        except stripe.error.StripeError as e:
            raise Exception(f"Stripe API error: {str(e)}") from e

    async def refund_payment(
        self,
        transaction_id: str,
        amount: float | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Refund a Stripe payment.

        Args:
            transaction_id: Stripe charge ID or payment intent ID
            amount: Amount to refund (None = full refund)
            reason: Refund reason

        Returns:
            RefundResult with refund details
        """
        stripe = self._get_stripe()

        try:
            # Build refund parameters
            refund_params: dict[str, Any] = {}

            # Determine if it's a charge or payment intent
            if transaction_id.startswith("pi_"):
                refund_params["payment_intent"] = transaction_id
            else:
                refund_params["charge"] = transaction_id

            # Add amount if partial refund
            if amount is not None:
                refund_params["amount"] = int(amount * 100)

            # Add reason if provided
            if reason:
                refund_params["reason"] = "requested_by_customer"
                refund_params["metadata"] = {"reason": reason}

            # Create refund
            refund = stripe.Refund.create(**refund_params)

            return RefundResult(
                refund_id=refund.id,
                amount=float(refund.amount / 100),
                currency=refund.currency.upper(),
                status=refund.status,
                metadata={"stripe_refund": refund.to_dict()},
            )

        except stripe.error.StripeError as e:
            raise Exception(f"Stripe API error: {str(e)}") from e

    async def verify_webhook(
        self,
        payload: bytes | dict[str, Any],
        signature: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify and parse Stripe webhook.

        Args:
            payload: Raw webhook payload (bytes)
            signature: Stripe-Signature header
            headers: HTTP headers

        Returns:
            Verified webhook event data

        Raises:
            Exception: If webhook verification fails
        """
        stripe = self._get_stripe()

        webhook_secret = self.get_credential("webhook_secret")
        if not webhook_secret:
            raise ValueError("Stripe webhook_secret not configured in credentials")

        if not signature:
            raise ValueError("Stripe-Signature header missing")

        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload=payload if isinstance(payload, bytes) else str(payload).encode(),
                sig_header=signature,
                secret=webhook_secret,
            )

            return event.to_dict()

        except stripe.error.SignatureVerificationError as e:
            raise Exception(f"Webhook signature verification failed: {str(e)}") from e
        except Exception as e:
            raise Exception(f"Webhook processing error: {str(e)}") from e

    def get_payment_method_info(self) -> dict[str, Any]:
        """Get Stripe payment method information.

        Returns:
            Payment method info dictionary
        """
        return {
            "name": "Stripe",
            "display_name": self.get_config("display_name", "Credit/Debit Card"),
            "type": "card",
            "supports_refund": True,
            "requires_redirect": False,
            "logo_url": "https://stripe.com/img/v3/home/social.png",
            "min_amount": self.get_config("min_amount", 0.50),  # €0.50 minimum
            "max_amount": self.get_config("max_amount", 999999.99),
        }

    def _map_stripe_status(self, stripe_status: str) -> str:
        """Map Stripe status to our internal status.

        Args:
            stripe_status: Stripe payment intent status

        Returns:
            Internal status string
        """
        status_map = {
            "requires_payment_method": "pending",
            "requires_confirmation": "pending",
            "requires_action": "requires_action",
            "processing": "processing",
            "requires_capture": "processing",
            "canceled": "cancelled",
            "succeeded": "succeeded",
        }
        return status_map.get(stripe_status, "pending")
