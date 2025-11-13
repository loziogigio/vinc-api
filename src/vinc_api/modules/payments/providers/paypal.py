"""PayPal payment provider implementation."""

import base64
from typing import Any

from .base import BasePaymentProvider, PaymentIntentResult, RefundResult


class PayPalProvider(BasePaymentProvider):
    """PayPal payment provider implementation.

    Uses PayPal Orders API v2 for processing payments.
    Supports PayPal wallet and PayPal Credit.
    """

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "paypal"

    def _get_base_url(self) -> str:
        """Get PayPal API base URL based on mode.

        Returns:
            API base URL
        """
        if self.is_test_mode():
            return "https://api-m.sandbox.paypal.com"
        return "https://api-m.paypal.com"

    def _get_auth_header(self) -> str:
        """Get Basic Auth header for PayPal API.

        Returns:
            Authorization header value

        Raises:
            ValueError: If credentials are missing
        """
        client_id = self.get_credential("client_id")
        client_secret = self.get_credential("client_secret")

        if not client_id or not client_secret:
            raise ValueError("PayPal client_id and client_secret required")

        credentials = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def _get_access_token(self) -> str:
        """Get PayPal OAuth access token.

        Returns:
            Access token

        Raises:
            Exception: If token request fails
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for PayPal. Install with: pip install httpx"
            ) from e

        url = f"{self._get_base_url()}/v1/oauth2/token"
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = "grant_type=client_credentials"

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, content=data)
            response.raise_for_status()
            result = response.json()
            return result["access_token"]

    async def _make_api_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request to PayPal.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., '/v2/checkout/orders')
            data: Request body data

        Returns:
            Response JSON

        Raises:
            Exception: If request fails
        """
        try:
            import httpx
        except ImportError as e:
            raise ImportError(
                "httpx library required for PayPal. Install with: pip install httpx"
            ) from e

        access_token = await self._get_access_token()
        url = f"{self._get_base_url()}{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method.upper() == "PATCH":
                response = await client.patch(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json() if response.content else {}

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
        """Create a PayPal Order (payment intent).

        Args:
            amount: Payment amount
            currency: Currency code (e.g., 'EUR', 'USD')
            order_id: Internal order ID
            customer_email: Customer email
            metadata: Additional metadata
            return_url: Return URL after payment
            cancel_url: Cancel URL

        Returns:
            PaymentIntentResult with order details
        """
        # Build order request
        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": order_id,
                    "amount": {
                        "currency_code": currency.upper(),
                        "value": f"{amount:.2f}",
                    },
                    "custom_id": order_id,
                }
            ],
            "application_context": {
                "brand_name": self.get_config("brand_name", "VINC"),
                "landing_page": "NO_PREFERENCE",
                "user_action": "PAY_NOW",
                "return_url": return_url or self.get_config("default_return_url", ""),
                "cancel_url": cancel_url or self.get_config("default_cancel_url", ""),
            },
        }

        try:
            # Create order
            result = await self._make_api_request(
                "POST",
                "/v2/checkout/orders",
                order_data,
            )

            # Extract approval URL
            approve_link = None
            for link in result.get("links", []):
                if link.get("rel") == "approve":
                    approve_link = link.get("href")
                    break

            return PaymentIntentResult(
                payment_intent_id=result["id"],
                client_secret=None,  # PayPal doesn't use client secrets
                redirect_url=approve_link,
                requires_action=True,  # PayPal always requires redirect
                status=self._map_paypal_status(result.get("status")),
                amount=amount,
                currency=currency,
                metadata={"paypal_order": result},
            )

        except Exception as e:
            raise Exception(f"PayPal API error: {str(e)}") from e

    async def confirm_payment(
        self,
        payment_intent_id: str,
        payment_data: dict[str, Any] | None = None,
    ) -> PaymentIntentResult:
        """Capture a PayPal Order (confirm payment).

        Args:
            payment_intent_id: PayPal order ID
            payment_data: Additional payment data

        Returns:
            Updated PaymentIntentResult
        """
        try:
            # Capture the order
            result = await self._make_api_request(
                "POST",
                f"/v2/checkout/orders/{payment_intent_id}/capture",
                {},
            )

            # Extract amount and currency from purchase units
            amount = 0.0
            currency = "EUR"
            if result.get("purchase_units"):
                first_unit = result["purchase_units"][0]
                amount = float(first_unit["payments"]["captures"][0]["amount"]["value"])
                currency = first_unit["payments"]["captures"][0]["amount"]["currency_code"]

            return PaymentIntentResult(
                payment_intent_id=result["id"],
                client_secret=None,
                redirect_url=None,
                requires_action=False,
                status=self._map_paypal_status(result.get("status")),
                amount=amount,
                currency=currency,
                metadata={"paypal_capture": result},
            )

        except Exception as e:
            raise Exception(f"PayPal API error: {str(e)}") from e

    async def get_payment_status(
        self,
        payment_intent_id: str,
    ) -> PaymentIntentResult:
        """Get status of a PayPal Order.

        Args:
            payment_intent_id: PayPal order ID

        Returns:
            PaymentIntentResult with current status
        """
        try:
            # Get order details
            result = await self._make_api_request(
                "GET",
                f"/v2/checkout/orders/{payment_intent_id}",
            )

            # Extract amount and currency
            amount = 0.0
            currency = "EUR"
            if result.get("purchase_units"):
                first_unit = result["purchase_units"][0]
                amount = float(first_unit["amount"]["value"])
                currency = first_unit["amount"]["currency_code"]

            # Extract approval URL
            approve_link = None
            for link in result.get("links", []):
                if link.get("rel") == "approve":
                    approve_link = link.get("href")
                    break

            return PaymentIntentResult(
                payment_intent_id=result["id"],
                client_secret=None,
                redirect_url=approve_link,
                requires_action=result.get("status") in ["CREATED", "APPROVED"],
                status=self._map_paypal_status(result.get("status")),
                amount=amount,
                currency=currency,
                metadata={"paypal_order": result},
            )

        except Exception as e:
            raise Exception(f"PayPal API error: {str(e)}") from e

    async def refund_payment(
        self,
        transaction_id: str,
        amount: float | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Refund a PayPal payment.

        Args:
            transaction_id: PayPal capture ID
            amount: Amount to refund (None = full refund)
            reason: Refund reason

        Returns:
            RefundResult with refund details
        """
        # Build refund request
        refund_data: dict[str, Any] = {}

        if amount is not None:
            refund_data["amount"] = {
                "value": f"{amount:.2f}",
                "currency_code": "EUR",  # TODO: Get from transaction
            }

        if reason:
            refund_data["note_to_payer"] = reason

        try:
            # Create refund
            result = await self._make_api_request(
                "POST",
                f"/v2/payments/captures/{transaction_id}/refund",
                refund_data if refund_data else None,
            )

            return RefundResult(
                refund_id=result["id"],
                amount=float(result["amount"]["value"]),
                currency=result["amount"]["currency_code"],
                status=result["status"],
                metadata={"paypal_refund": result},
            )

        except Exception as e:
            raise Exception(f"PayPal API error: {str(e)}") from e

    async def verify_webhook(
        self,
        payload: bytes | dict[str, Any],
        signature: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify and parse PayPal webhook.

        Args:
            payload: Webhook payload
            signature: PayPal signature headers
            headers: HTTP headers

        Returns:
            Verified webhook event data

        Note:
            PayPal webhook verification requires calling their API.
            For simplicity, we'll parse the payload and validate basic structure.
        """
        # Parse payload if it's bytes
        if isinstance(payload, bytes):
            import json

            event_data = json.loads(payload.decode())
        else:
            event_data = payload

        # Validate basic structure
        if not event_data.get("event_type"):
            raise ValueError("Invalid PayPal webhook: missing event_type")

        # TODO: Implement full webhook verification using PayPal API
        # https://developer.paypal.com/api/rest/webhooks/rest/#verify-webhook-signature

        return event_data

    def get_payment_method_info(self) -> dict[str, Any]:
        """Get PayPal payment method information.

        Returns:
            Payment method info dictionary
        """
        return {
            "name": "PayPal",
            "display_name": self.get_config("display_name", "PayPal"),
            "type": "digital_wallet",
            "supports_refund": True,
            "requires_redirect": True,
            "logo_url": "https://www.paypalobjects.com/webstatic/icon/pp258.png",
            "min_amount": self.get_config("min_amount", 1.00),
            "max_amount": self.get_config("max_amount", 999999.99),
        }

    def _map_paypal_status(self, paypal_status: str | None) -> str:
        """Map PayPal status to our internal status.

        Args:
            paypal_status: PayPal order status

        Returns:
            Internal status string
        """
        status_map = {
            "CREATED": "pending",
            "SAVED": "pending",
            "APPROVED": "processing",
            "VOIDED": "cancelled",
            "COMPLETED": "succeeded",
            "PAYER_ACTION_REQUIRED": "requires_action",
        }
        return status_map.get(paypal_status or "", "pending")
