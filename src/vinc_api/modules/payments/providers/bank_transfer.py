"""Bank Transfer payment provider implementation.

Manual bank transfer tracking system for traditional wire transfers.
No external API - handles tracking and confirmation of bank transfers.
"""

from typing import Any

from .base import BasePaymentProvider, PaymentIntentResult, RefundResult


class BankTransferProvider(BasePaymentProvider):
    """Bank Transfer payment provider implementation.

    Handles manual bank transfer payments without external API integration.
    Provides payment instructions and tracks transfer confirmations.
    """

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "bank_transfer"

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
        """Create a bank transfer payment instruction.

        Args:
            amount: Payment amount
            currency: Currency code
            order_id: Internal order ID
            customer_email: Customer email
            metadata: Additional metadata
            return_url: Return URL (not used for bank transfer)
            cancel_url: Cancel URL (not used for bank transfer)

        Returns:
            PaymentIntentResult with bank details
        """
        # Generate unique payment reference
        import hashlib
        reference = f"BT-{order_id[:8]}-{hashlib.md5(order_id.encode()).hexdigest()[:6].upper()}"

        # Get bank account details from configuration
        bank_details = {
            "bank_name": self.get_config("bank_name", "Banca Example"),
            "account_holder": self.get_config("account_holder", "Example Company S.r.l."),
            "iban": self.get_config("iban", "IT60X0542811101000000123456"),
            "bic": self.get_config("bic", "BPMOIT22"),
            "reference": reference,
            "amount": f"{amount:.2f}",
            "currency": currency,
        }

        # Build payment instructions
        instructions = f"""
Bank Transfer Payment Instructions:

Amount: {amount:.2f} {currency}
Reference: {reference}

Bank Details:
Bank Name: {bank_details['bank_name']}
Account Holder: {bank_details['account_holder']}
IBAN: {bank_details['iban']}
BIC/SWIFT: {bank_details['bic']}

IMPORTANT: Please include the reference "{reference}" in the transfer description.

Payment will be processed within 1-3 business days after receiving the transfer.
You will receive a confirmation email at {customer_email}.
"""

        return PaymentIntentResult(
            payment_intent_id=reference,
            client_secret=None,
            redirect_url=None,
            requires_action=True,  # Customer must make transfer
            status="pending",
            amount=amount,
            currency=currency,
            metadata={
                "bank_transfer": {
                    "reference": reference,
                    "bank_details": bank_details,
                    "instructions": instructions,
                    "customer_email": customer_email,
                }
            },
        )

    async def confirm_payment(
        self,
        payment_intent_id: str,
        payment_data: dict[str, Any] | None = None,
    ) -> PaymentIntentResult:
        """Confirm a bank transfer payment.

        This should be called manually when the transfer is received.

        Args:
            payment_intent_id: Bank transfer reference
            payment_data: Additional confirmation data (amount received, date, etc.)

        Returns:
            Updated PaymentIntentResult
        """
        payment_data = payment_data or {}

        # Mark as succeeded
        return PaymentIntentResult(
            payment_intent_id=payment_intent_id,
            client_secret=None,
            redirect_url=None,
            requires_action=False,
            status="succeeded",
            amount=payment_data.get("amount", 0.0),
            currency=payment_data.get("currency", "EUR"),
            metadata={
                "bank_transfer": {
                    "reference": payment_intent_id,
                    "confirmed_at": payment_data.get("confirmed_at"),
                    "confirmed_by": payment_data.get("confirmed_by"),
                    "bank_transaction_id": payment_data.get("bank_transaction_id"),
                }
            },
        )

    async def get_payment_status(
        self,
        payment_intent_id: str,
    ) -> PaymentIntentResult:
        """Get status of a bank transfer.

        Since bank transfers are manual, this returns pending status.
        Status must be updated manually when transfer is confirmed.

        Args:
            payment_intent_id: Bank transfer reference

        Returns:
            PaymentIntentResult with current status
        """
        # Bank transfer status must be tracked in database
        # This method just returns pending as default
        return PaymentIntentResult(
            payment_intent_id=payment_intent_id,
            client_secret=None,
            redirect_url=None,
            requires_action=True,
            status="pending",
            amount=0.0,
            currency="EUR",
            metadata={
                "bank_transfer": {
                    "reference": payment_intent_id,
                    "status": "awaiting_transfer",
                }
            },
        )

    async def refund_payment(
        self,
        transaction_id: str,
        amount: float | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Process a bank transfer refund.

        For bank transfers, refunds must be processed manually.
        This creates a refund record that should be executed via bank transfer.

        Args:
            transaction_id: Bank transfer reference
            amount: Amount to refund
            reason: Refund reason

        Returns:
            RefundResult with refund details
        """
        # Generate refund reference
        import hashlib
        import datetime

        refund_ref = f"REFUND-{transaction_id[:8]}-{hashlib.md5(str(datetime.datetime.now()).encode()).hexdigest()[:6].upper()}"

        # Refund must be processed manually via bank transfer
        refund_amount = amount or 0.0

        return RefundResult(
            refund_id=refund_ref,
            amount=refund_amount,
            currency="EUR",
            status="pending",  # Pending manual execution
            metadata={
                "bank_transfer_refund": {
                    "reference": refund_ref,
                    "original_transaction": transaction_id,
                    "reason": reason,
                    "status": "pending_execution",
                    "instructions": f"Process bank transfer refund of {refund_amount:.2f} EUR for reference {transaction_id}",
                }
            },
        )

    async def verify_webhook(
        self,
        payload: bytes | dict[str, Any],
        signature: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify webhook (not applicable for bank transfer).

        Bank transfers don't have webhooks. Status updates are manual.

        Args:
            payload: Webhook payload
            signature: Webhook signature
            headers: HTTP headers

        Returns:
            Parsed payload

        Raises:
            NotImplementedError: Bank transfers don't support webhooks
        """
        raise NotImplementedError("Bank transfer provider does not support webhooks")

    def get_payment_method_info(self) -> dict[str, Any]:
        """Get bank transfer payment method information.

        Returns:
            Payment method info dictionary
        """
        return {
            "name": "Bank Transfer",
            "display_name": self.get_config("display_name", "Bonifico Bancario"),
            "type": "bank_transfer",
            "supports_refund": True,  # Manual refunds
            "requires_redirect": False,
            "logo_url": None,
            "min_amount": self.get_config("min_amount", 0.01),
            "max_amount": self.get_config("max_amount", 999999.99),
            "processing_time": self.get_config("processing_time", "1-3 business days"),
        }
