"""Stripe webhook handler."""

import time
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models import PaymentTransaction, PaymentWebhookLog, TenantPaymentProvider
from ..providers.stripe import StripeProvider
from ..schemas import PaymentStatus
from ..utils.encryption import get_encryption_handler


class StripeWebhookHandler:
    """Handler for Stripe webhook events."""

    def __init__(self, db: Session):
        """Initialize webhook handler.

        Args:
            db: Database session
        """
        self.db = db
        self.encryption = get_encryption_handler()

    async def handle(self, payload: bytes, signature: str | None) -> dict[str, str]:
        """Handle Stripe webhook.

        Args:
            payload: Raw webhook payload
            signature: Stripe-Signature header

        Returns:
            Success response
        """
        start_time = time.time()
        event_data: dict[str, Any] | None = None
        event_id: str | None = None
        event_type: str | None = None
        transaction_id: str | None = None
        processing_status = "failed"
        error_message: str | None = None

        try:
            # Parse the event (we'll verify it later with proper credentials)
            import json

            event_dict = json.loads(payload.decode())
            event_id = event_dict.get("id")
            event_type = event_dict.get("type")
            event_data = event_dict

            # Check for duplicate webhook
            if event_id:
                stmt = select(PaymentWebhookLog).where(
                    and_(
                        PaymentWebhookLog.provider == "stripe",
                        PaymentWebhookLog.event_id == event_id,
                        PaymentWebhookLog.status == "success",
                    )
                )
                existing = self.db.execute(stmt).scalar_one_or_none()
                if existing:
                    # Duplicate webhook, ignore
                    return {"status": "duplicate"}

            # Extract payment intent ID from event
            payment_intent_id = None
            if event_type and "payment_intent" in event_type:
                payment_intent_id = event_dict.get("data", {}).get("object", {}).get("id")

            if not payment_intent_id:
                # Can't process without payment intent ID
                error_message = "No payment intent ID in webhook"
                return {"status": "ignored"}

            # Find transaction by payment intent ID
            stmt = select(PaymentTransaction, TenantPaymentProvider).join(
                TenantPaymentProvider,
                and_(
                    TenantPaymentProvider.tenant_id == PaymentTransaction.tenant_id,
                    TenantPaymentProvider.provider == PaymentTransaction.provider,
                ),
            ).where(
                and_(
                    PaymentTransaction.provider_payment_intent_id == payment_intent_id,
                    PaymentTransaction.provider == "stripe",
                )
            )

            result = self.db.execute(stmt).first()
            if not result:
                error_message = f"Transaction not found for payment intent {payment_intent_id}"
                return {"status": "ignored"}

            transaction, tenant_provider = result
            transaction_id = str(transaction.id)

            # Verify webhook signature with tenant's credentials
            credentials = self.encryption.decrypt(tenant_provider.credentials)
            provider = StripeProvider(
                credentials=credentials,
                mode=tenant_provider.mode,
                config=tenant_provider.config,
            )

            # Verify the webhook
            verified_event = await provider.verify_webhook(
                payload=payload,
                signature=signature,
                headers=None,
            )

            # Process the event based on type
            await self._process_event(
                event_type=verified_event["type"],
                event_data=verified_event["data"]["object"],
                transaction=transaction,
            )

            processing_status = "success"
            return {"status": "success"}

        except Exception as e:
            error_message = str(e)
            processing_status = "failed"
            return {"status": "error", "message": str(e)}

        finally:
            # Log the webhook
            processing_time_ms = int((time.time() - start_time) * 1000)
            webhook_log = PaymentWebhookLog(
                provider="stripe",
                event_type=event_type,
                event_id=event_id,
                payload=event_data or {},
                signature=signature,
                headers=None,
                status=processing_status,
                error_message=error_message,
                processing_time_ms=processing_time_ms,
                transaction_id=transaction_id,
                processed_at=datetime.utcnow(),
            )
            self.db.add(webhook_log)
            self.db.commit()

    async def _process_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        transaction: PaymentTransaction,
    ) -> None:
        """Process a Stripe webhook event.

        Args:
            event_type: Stripe event type
            event_data: Event data
            transaction: Payment transaction to update
        """
        # Add webhook event to transaction log
        transaction.webhook_events.append(
            {
                "event_type": event_type,
                "received_at": datetime.utcnow().isoformat(),
                "event_id": event_data.get("id"),
            }
        )

        # Update transaction based on event type
        if event_type == "payment_intent.succeeded":
            transaction.status = PaymentStatus.SUCCEEDED.value
            transaction.completed_at = datetime.utcnow()
            transaction.provider_transaction_id = event_data.get("charges", {}).get(
                "data", [{}]
            )[0].get("id")

        elif event_type == "payment_intent.payment_failed":
            transaction.status = PaymentStatus.FAILED.value
            transaction.completed_at = datetime.utcnow()
            transaction.error_message = event_data.get("last_payment_error", {}).get(
                "message", "Payment failed"
            )

        elif event_type == "payment_intent.canceled":
            transaction.status = PaymentStatus.CANCELLED.value
            transaction.completed_at = datetime.utcnow()

        elif event_type == "payment_intent.processing":
            transaction.status = PaymentStatus.PROCESSING.value

        elif event_type == "payment_intent.requires_action":
            transaction.status = PaymentStatus.REQUIRES_ACTION.value

        elif event_type == "charge.refunded":
            # Handle refund
            refund_data = event_data.get("refunds", {}).get("data", [])
            if refund_data:
                total_refunded = sum(r.get("amount", 0) for r in refund_data) / 100
                transaction.refunded_amount = total_refunded
                if total_refunded >= float(transaction.amount):
                    transaction.status = PaymentStatus.REFUNDED.value
                else:
                    transaction.status = PaymentStatus.PARTIALLY_REFUNDED.value

        transaction.updated_at = datetime.utcnow()
        self.db.commit()
