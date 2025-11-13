"""PayPal webhook handler."""

import time
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models import PaymentTransaction, PaymentWebhookLog, TenantPaymentProvider
from ..providers.paypal import PayPalProvider
from ..schemas import PaymentStatus
from ..utils.encryption import get_encryption_handler


class PayPalWebhookHandler:
    """Handler for PayPal webhook events."""

    def __init__(self, db: Session):
        """Initialize webhook handler.

        Args:
            db: Database session
        """
        self.db = db
        self.encryption = get_encryption_handler()

    async def handle(
        self, payload: dict[str, Any], headers: dict[str, Any]
    ) -> dict[str, str]:
        """Handle PayPal webhook.

        Args:
            payload: Webhook payload (already parsed JSON)
            headers: HTTP headers

        Returns:
            Success response
        """
        start_time = time.time()
        event_type: str | None = None
        event_id: str | None = None
        transaction_id: str | None = None
        processing_status = "failed"
        error_message: str | None = None

        try:
            event_type = payload.get("event_type")
            event_id = payload.get("id")

            # Check for duplicate webhook
            if event_id:
                stmt = select(PaymentWebhookLog).where(
                    and_(
                        PaymentWebhookLog.provider == "paypal",
                        PaymentWebhookLog.event_id == event_id,
                        PaymentWebhookLog.status == "success",
                    )
                )
                existing = self.db.execute(stmt).scalar_one_or_none()
                if existing:
                    # Duplicate webhook, ignore
                    return {"status": "duplicate"}

            # Extract order ID or capture ID from event
            resource = payload.get("resource", {})
            order_id = None
            capture_id = None

            if "CHECKOUT.ORDER" in event_type:  # type: ignore
                order_id = resource.get("id")
            elif "PAYMENT.CAPTURE" in event_type:  # type: ignore
                capture_id = resource.get("id")
                # Try to get order ID from supplementary data
                order_id = resource.get("supplementary_data", {}).get(
                    "related_ids", {}
                ).get("order_id")

            if not order_id:
                error_message = "No order ID in webhook"
                return {"status": "ignored"}

            # Find transaction by payment intent ID (order ID)
            stmt = select(PaymentTransaction, TenantPaymentProvider).join(
                TenantPaymentProvider,
                and_(
                    TenantPaymentProvider.tenant_id == PaymentTransaction.tenant_id,
                    TenantPaymentProvider.provider == PaymentTransaction.provider,
                ),
            ).where(
                and_(
                    PaymentTransaction.provider_payment_intent_id == order_id,
                    PaymentTransaction.provider == "paypal",
                )
            )

            result = self.db.execute(stmt).first()
            if not result:
                error_message = f"Transaction not found for order {order_id}"
                return {"status": "ignored"}

            transaction, tenant_provider = result
            transaction_id = str(transaction.id)

            # Verify webhook (basic validation)
            credentials = self.encryption.decrypt(tenant_provider.credentials)
            provider = PayPalProvider(
                credentials=credentials,
                mode=tenant_provider.mode,
                config=tenant_provider.config,
            )

            # Verify the webhook
            verified_event = await provider.verify_webhook(
                payload=payload,
                signature=None,
                headers=headers,
            )

            # Process the event based on type
            await self._process_event(
                event_type=verified_event["event_type"],
                event_data=verified_event,
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
                provider="paypal",
                event_type=event_type,
                event_id=event_id,
                payload=payload,
                signature=None,
                headers=headers,
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
        """Process a PayPal webhook event.

        Args:
            event_type: PayPal event type
            event_data: Event data
            transaction: Payment transaction to update
        """
        resource = event_data.get("resource", {})

        # Add webhook event to transaction log
        transaction.webhook_events.append(
            {
                "event_type": event_type,
                "received_at": datetime.utcnow().isoformat(),
                "event_id": event_data.get("id"),
            }
        )

        # Update transaction based on event type
        if event_type == "CHECKOUT.ORDER.APPROVED":
            transaction.status = PaymentStatus.PROCESSING.value

        elif event_type == "CHECKOUT.ORDER.COMPLETED":
            transaction.status = PaymentStatus.SUCCEEDED.value
            transaction.completed_at = datetime.utcnow()

        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            transaction.status = PaymentStatus.SUCCEEDED.value
            transaction.completed_at = datetime.utcnow()
            transaction.provider_transaction_id = resource.get("id")

        elif event_type == "PAYMENT.CAPTURE.DENIED":
            transaction.status = PaymentStatus.FAILED.value
            transaction.completed_at = datetime.utcnow()
            transaction.error_message = "Payment capture denied"

        elif event_type == "PAYMENT.CAPTURE.REFUNDED":
            # Handle refund
            refund_amount = float(resource.get("amount", {}).get("value", 0))
            transaction.refunded_amount = float(transaction.refunded_amount) + refund_amount
            if transaction.refunded_amount >= float(transaction.amount):
                transaction.status = PaymentStatus.REFUNDED.value
            else:
                transaction.status = PaymentStatus.PARTIALLY_REFUNDED.value

        elif event_type == "CHECKOUT.ORDER.VOIDED":
            transaction.status = PaymentStatus.CANCELLED.value
            transaction.completed_at = datetime.utcnow()

        transaction.updated_at = datetime.utcnow()
        self.db.commit()
