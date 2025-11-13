"""Nexi payment provider implementation.

Nexi is Italy's leading payment provider, offering card payments and digital solutions.
This implementation uses Nexi's XPay API for payment processing.
"""

from typing import Any

from .base import BasePaymentProvider, PaymentIntentResult, RefundResult


class NexiProvider(BasePaymentProvider):
    """Nexi payment provider implementation.

    Supports credit/debit card payments through Nexi's XPay platform.
    Popular in Italy for e-commerce transactions.
    """

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "nexi"

    def _get_base_url(self) -> str:
        """Get Nexi API base URL based on mode.

        Returns:
            API base URL
        """
        if self.is_test_mode():
            return "https://int-ecommerce.nexi.it"
        return "https://ecommerce.nexi.it"

    def _get_api_key(self) -> str:
        """Get API key for authentication.

        Returns:
            API key

        Raises:
            ValueError: If API key not configured
        """
        api_key = self.get_credential("api_key")
        if not api_key:
            raise ValueError("Nexi api_key not configured in credentials")
        return api_key

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
        """Create a Nexi payment order.

        Args:
            amount: Payment amount in decimal (e.g., 10.50 for €10.50)
            currency: Currency code (e.g., 'EUR')
            order_id: Internal order ID
            customer_email: Customer email
            metadata: Additional metadata
            return_url: Return URL after payment
            cancel_url: Cancel URL

        Returns:
            PaymentIntentResult with payment details
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for Nexi. Install with: pip install httpx"
            ) from e

        # Convert amount to cents
        amount_cents = int(amount * 100)

        # Build payment request
        payment_data = {
            "amount": amount_cents,
            "currency": currency.upper(),
            "transactionId": order_id,
            "description": f"Order {order_id}",
            "customerId": customer_email,
            "urlBack": return_url or self.get_config("default_return_url", ""),
            "urlPost": self.get_config("webhook_url", ""),
            "languageId": self.get_config("language", "ITA"),
            "customFields": metadata or {},
        }

        try:
            # Make API request
            url = f"{self._get_base_url()}/ecomm/api/bo/payment/create"
            headers = {
                "X-Api-Key": self._get_api_key(),
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=payment_data)
                response.raise_for_status()
                result = response.json()

            # Extract redirect URL
            redirect_url = result.get("redirectUrl")
            payment_id = result.get("paymentId")

            return PaymentIntentResult(
                payment_intent_id=payment_id or order_id,
                client_secret=None,  # Nexi doesn't use client secrets
                redirect_url=redirect_url,
                requires_action=True,  # Nexi requires redirect
                status="pending",
                amount=amount,
                currency=currency,
                metadata={"nexi_payment": result},
            )

        except Exception as e:
            raise Exception(f"Nexi API error: {str(e)}") from e

    async def confirm_payment(
        self,
        payment_intent_id: str,
        payment_data: dict[str, Any] | None = None,
    ) -> PaymentIntentResult:
        """Confirm a Nexi payment.

        Nexi payments are confirmed automatically after redirect.
        This method retrieves the current status.

        Args:
            payment_intent_id: Nexi payment ID
            payment_data: Additional payment data

        Returns:
            Updated PaymentIntentResult
        """
        return await self.get_payment_status(payment_intent_id)

    async def get_payment_status(
        self,
        payment_intent_id: str,
    ) -> PaymentIntentResult:
        """Get status of a Nexi payment.

        Args:
            payment_intent_id: Nexi payment ID

        Returns:
            PaymentIntentResult with current status
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for Nexi. Install with: pip install httpx"
            ) from e

        try:
            # Query payment status
            url = f"{self._get_base_url()}/ecomm/api/bo/payment/info/{payment_intent_id}"
            headers = {
                "X-Api-Key": self._get_api_key(),
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                result = response.json()

            status = result.get("status", "pending")
            amount_cents = result.get("amount", 0)

            return PaymentIntentResult(
                payment_intent_id=payment_intent_id,
                client_secret=None,
                redirect_url=None,
                requires_action=status in ["pending", "authorized"],
                status=self._map_nexi_status(status),
                amount=float(amount_cents / 100),
                currency=result.get("currency", "EUR"),
                metadata={"nexi_payment": result},
            )

        except Exception as e:
            raise Exception(f"Nexi API error: {str(e)}") from e

    async def refund_payment(
        self,
        transaction_id: str,
        amount: float | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Refund a Nexi payment.

        Args:
            transaction_id: Nexi payment ID
            amount: Amount to refund (None = full refund)
            reason: Refund reason

        Returns:
            RefundResult with refund details
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for Nexi. Install with: pip install httpx"
            ) from e

        # Convert amount to cents
        amount_cents = int(amount * 100) if amount else None

        # Build refund request
        refund_data = {
            "paymentId": transaction_id,
            "amount": amount_cents,
            "description": reason or "Refund requested",
        }

        try:
            # Make refund request
            url = f"{self._get_base_url()}/ecomm/api/bo/payment/refund"
            headers = {
                "X-Api-Key": self._get_api_key(),
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=refund_data)
                response.raise_for_status()
                result = response.json()

            refund_id = result.get("refundId", transaction_id)
            refunded_amount = result.get("amount", amount_cents or 0) / 100

            return RefundResult(
                refund_id=refund_id,
                amount=refunded_amount,
                currency=result.get("currency", "EUR"),
                status=result.get("status", "pending"),
                metadata={"nexi_refund": result},
            )

        except Exception as e:
            raise Exception(f"Nexi API error: {str(e)}") from e

    async def verify_webhook(
        self,
        payload: bytes | dict[str, Any],
        signature: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify and parse Nexi webhook.

        Args:
            payload: Webhook payload
            signature: Webhook signature (MAC)
            headers: HTTP headers

        Returns:
            Verified webhook event data

        Raises:
            Exception: If webhook verification fails
        """
        import hashlib
        import hmac

        webhook_secret = self.get_credential("webhook_secret")
        if not webhook_secret:
            raise ValueError("Nexi webhook_secret not configured")

        # Parse payload
        if isinstance(payload, bytes):
            import json
            event_data = json.loads(payload.decode())
        else:
            event_data = payload

        # Verify MAC signature
        if signature:
            # Nexi uses HMAC-SHA256 for webhook verification
            expected_signature = hmac.new(
                webhook_secret.encode(),
                payload if isinstance(payload, bytes) else str(payload).encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected_signature, signature):
                raise Exception("Webhook signature verification failed")

        return event_data

    def get_payment_method_info(self) -> dict[str, Any]:
        """Get Nexi payment method information.

        Returns:
            Payment method info dictionary
        """
        return {
            "name": "Nexi",
            "display_name": self.get_config("display_name", "Carta di Credito/Debito"),
            "type": "card",
            "supports_refund": True,
            "requires_redirect": True,
            "logo_url": "https://www.nexi.it/content/dam/nexi/logo/logo-nexi.svg",
            "min_amount": self.get_config("min_amount", 0.01),
            "max_amount": self.get_config("max_amount", 999999.99),
        }

    def _map_nexi_status(self, nexi_status: str) -> str:
        """Map Nexi status to our internal status.

        Args:
            nexi_status: Nexi payment status

        Returns:
            Internal status string
        """
        status_map = {
            "pending": "pending",
            "authorized": "processing",
            "captured": "succeeded",
            "cancelled": "cancelled",
            "declined": "failed",
            "refunded": "refunded",
        }
        return status_map.get(nexi_status.lower(), "pending")
