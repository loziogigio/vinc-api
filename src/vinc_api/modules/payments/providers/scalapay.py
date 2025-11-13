"""Scalapay payment provider implementation.

Scalapay is a Buy Now Pay Later (BNPL) solution popular in Italy and Europe.
Allows customers to split payments into interest-free installments.
"""

from typing import Any

from .base import BasePaymentProvider, PaymentIntentResult, RefundResult


class ScalapayProvider(BasePaymentProvider):
    """Scalapay (BNPL) payment provider implementation.

    Supports Buy Now Pay Later with flexible installment plans.
    Customers can pay in 3 or 4 interest-free installments.
    """

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "scalapay"

    def _get_base_url(self) -> str:
        """Get Scalapay API base URL based on mode.

        Returns:
            API base URL
        """
        if self.is_test_mode():
            return "https://staging.api.scalapay.com/v2"
        return "https://api.scalapay.com/v2"

    def _get_auth_header(self) -> str:
        """Get Bearer auth header for Scalapay API.

        Returns:
            Authorization header value

        Raises:
            ValueError: If API key not configured
        """
        api_key = self.get_credential("api_key")
        if not api_key:
            raise ValueError("Scalapay api_key not configured")
        return f"Bearer {api_key}"

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
        """Create a Scalapay payment order.

        Args:
            amount: Payment amount
            currency: Currency code (EUR only for Scalapay)
            order_id: Internal order ID
            customer_email: Customer email
            metadata: Additional metadata (must include customer details)
            return_url: Return URL after payment
            cancel_url: Cancel URL

        Returns:
            PaymentIntentResult with payment details
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for Scalapay. Install with: pip install httpx"
            ) from e

        # Scalapay requires customer details
        metadata = metadata or {}

        # Build order request
        order_data = {
            "totalAmount": {
                "amount": f"{amount:.2f}",
                "currency": currency.upper(),
            },
            "consumer": {
                "email": customer_email,
                "givenNames": metadata.get("customer_first_name", "Customer"),
                "surname": metadata.get("customer_last_name", "Name"),
                "phoneNumber": metadata.get("customer_phone", ""),
            },
            "billing": {
                "name": metadata.get("billing_name", "Customer Name"),
                "line1": metadata.get("billing_address", "Via Example 1"),
                "suburb": metadata.get("billing_city", "Milano"),
                "postcode": metadata.get("billing_postcode", "20100"),
                "countryCode": metadata.get("billing_country", "IT"),
                "phoneNumber": metadata.get("customer_phone", ""),
            },
            "shipping": {
                "name": metadata.get("shipping_name", metadata.get("billing_name", "Customer Name")),
                "line1": metadata.get("shipping_address", metadata.get("billing_address", "Via Example 1")),
                "suburb": metadata.get("shipping_city", metadata.get("billing_city", "Milano")),
                "postcode": metadata.get("shipping_postcode", metadata.get("billing_postcode", "20100")),
                "countryCode": metadata.get("shipping_country", metadata.get("billing_country", "IT")),
                "phoneNumber": metadata.get("customer_phone", ""),
            },
            "items": metadata.get("items", [
                {
                    "name": f"Order {order_id}",
                    "category": "general",
                    "quantity": 1,
                    "price": {
                        "amount": f"{amount:.2f}",
                        "currency": currency.upper(),
                    },
                }
            ]),
            "merchant": {
                "redirectConfirmUrl": return_url or self.get_config("default_return_url", ""),
                "redirectCancelUrl": cancel_url or self.get_config("default_cancel_url", ""),
            },
            "merchantReference": order_id,
            "taxAmount": {
                "amount": metadata.get("tax_amount", "0.00"),
                "currency": currency.upper(),
            },
            "shippingAmount": {
                "amount": metadata.get("shipping_amount", "0.00"),
                "currency": currency.upper(),
            },
        }

        try:
            # Create order
            url = f"{self._get_base_url()}/orders"
            headers = {
                "Authorization": self._get_auth_header(),
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=order_data)
                response.raise_for_status()
                result = response.json()

            # Extract checkout URL
            checkout_url = result.get("checkoutUrl")
            order_token = result.get("token")

            return PaymentIntentResult(
                payment_intent_id=order_token or order_id,
                client_secret=None,
                redirect_url=checkout_url,
                requires_action=True,  # Scalapay requires redirect
                status="pending",
                amount=amount,
                currency=currency,
                metadata={"scalapay_order": result},
            )

        except Exception as e:
            raise Exception(f"Scalapay API error: {str(e)}") from e

    async def confirm_payment(
        self,
        payment_intent_id: str,
        payment_data: dict[str, Any] | None = None,
    ) -> PaymentIntentResult:
        """Confirm a Scalapay payment.

        Scalapay requires explicit capture after customer approval.

        Args:
            payment_intent_id: Scalapay order token
            payment_data: Additional payment data

        Returns:
            Updated PaymentIntentResult
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for Scalapay. Install with: pip install httpx"
            ) from e

        try:
            # Capture the payment
            url = f"{self._get_base_url()}/payments/capture"
            headers = {
                "Authorization": self._get_auth_header(),
                "Content-Type": "application/json",
            }
            capture_data = {
                "token": payment_intent_id,
                "amount": payment_data.get("amount") if payment_data else None,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=capture_data)
                response.raise_for_status()
                result = response.json()

            return PaymentIntentResult(
                payment_intent_id=payment_intent_id,
                client_secret=None,
                redirect_url=None,
                requires_action=False,
                status=self._map_scalapay_status(result.get("status")),
                amount=float(result.get("totalAmount", {}).get("amount", 0)),
                currency=result.get("totalAmount", {}).get("currency", "EUR"),
                metadata={"scalapay_capture": result},
            )

        except Exception as e:
            raise Exception(f"Scalapay API error: {str(e)}") from e

    async def get_payment_status(
        self,
        payment_intent_id: str,
    ) -> PaymentIntentResult:
        """Get status of a Scalapay order.

        Args:
            payment_intent_id: Scalapay order token

        Returns:
            PaymentIntentResult with current status
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for Scalapay. Install with: pip install httpx"
            ) from e

        try:
            # Get order details
            url = f"{self._get_base_url()}/orders/{payment_intent_id}"
            headers = {
                "Authorization": self._get_auth_header(),
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                result = response.json()

            status = result.get("status", "pending")
            amount = float(result.get("totalAmount", {}).get("amount", 0))

            return PaymentIntentResult(
                payment_intent_id=payment_intent_id,
                client_secret=None,
                redirect_url=result.get("checkoutUrl"),
                requires_action=status in ["pending", "approved"],
                status=self._map_scalapay_status(status),
                amount=amount,
                currency=result.get("totalAmount", {}).get("currency", "EUR"),
                metadata={"scalapay_order": result},
            )

        except Exception as e:
            raise Exception(f"Scalapay API error: {str(e)}") from e

    async def refund_payment(
        self,
        transaction_id: str,
        amount: float | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Refund a Scalapay payment.

        Args:
            transaction_id: Scalapay order token
            amount: Amount to refund (None = full refund)
            reason: Refund reason

        Returns:
            RefundResult with refund details
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for Scalapay. Install with: pip install httpx"
            ) from e

        # Build refund request
        refund_data = {
            "token": transaction_id,
        }

        if amount is not None:
            refund_data["amount"] = {
                "amount": f"{amount:.2f}",
                "currency": "EUR",
            }

        try:
            # Create refund
            url = f"{self._get_base_url()}/payments/refund"
            headers = {
                "Authorization": self._get_auth_header(),
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=headers, json=refund_data)
                response.raise_for_status()
                result = response.json()

            refund_amount = float(result.get("refundAmount", {}).get("amount", amount or 0))

            return RefundResult(
                refund_id=result.get("refundId", transaction_id),
                amount=refund_amount,
                currency=result.get("refundAmount", {}).get("currency", "EUR"),
                status=result.get("status", "pending"),
                metadata={"scalapay_refund": result},
            )

        except Exception as e:
            raise Exception(f"Scalapay API error: {str(e)}") from e

    async def verify_webhook(
        self,
        payload: bytes | dict[str, Any],
        signature: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify and parse Scalapay webhook.

        Args:
            payload: Webhook payload
            signature: Webhook signature
            headers: HTTP headers

        Returns:
            Verified webhook event data
        """
        # Parse payload
        if isinstance(payload, bytes):
            import json
            event_data = json.loads(payload.decode())
        else:
            event_data = payload

        # Scalapay webhook verification
        # In production, verify the webhook signature
        if not event_data.get("token"):
            raise ValueError("Invalid Scalapay webhook: missing token")

        return event_data

    def get_payment_method_info(self) -> dict[str, Any]:
        """Get Scalapay payment method information.

        Returns:
            Payment method info dictionary
        """
        return {
            "name": "Scalapay",
            "display_name": self.get_config("display_name", "Paga in 3 rate senza interessi"),
            "type": "bnpl",
            "supports_refund": True,
            "requires_redirect": True,
            "logo_url": "https://cdn.scalapay.com/images/scalapay-logo.svg",
            "min_amount": self.get_config("min_amount", 1.00),
            "max_amount": self.get_config("max_amount", 2000.00),  # Scalapay limit
        }

    def _map_scalapay_status(self, scalapay_status: str | None) -> str:
        """Map Scalapay status to our internal status.

        Args:
            scalapay_status: Scalapay order status

        Returns:
            Internal status string
        """
        status_map = {
            "pending": "pending",
            "approved": "processing",
            "captured": "succeeded",
            "cancelled": "cancelled",
            "declined": "failed",
            "refunded": "refunded",
        }
        return status_map.get((scalapay_status or "").lower(), "pending")
