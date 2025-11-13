"""Banca Sella webhook handler."""

import time
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models import PaymentTransaction, PaymentWebhookLog, TenantPaymentProvider
from ..providers.banca_sella import BancaSellaProvider
from ..schemas import PaymentStatus
from ..utils.encryption import get_encryption_handler


class BancaSellaWebhookHandler:
    """Handler for Banca Sella webhook events."""

    def __init__(self, db: Session):
        """Initialize webhook handler.

        Args:
            db: Database session
        """
        self.db = db
        self.encryption = get_encryption_handler()

    async def handle(
        self, payload: bytes | dict[str, Any], signature: str | None, headers: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """Handle Banca Sella webhook.

        Args:
            payload: Webhook payload
            signature: Banca Sella signature
            headers: HTTP headers

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
            # Parse payload
            if isinstance(payload, bytes):
                import json

                event_data = json.loads(payload.decode())
            else:
                event_data = payload

            event_id = event_data.get("shopTransactionId")
            event_type = event_data.get("eventType", "payment_update")

            # Check for duplicate
            if event_id:
                stmt = select(PaymentWebhookLog).where(
                    and_(
                        PaymentWebhookLog.provider == "banca_sella",
                        PaymentWebhookLog.event_id == event_id,
                        PaymentWebhookLog.status == "success",
                    )
                )
                existing = self.db.execute(stmt).scalar_one_or_none()
                if existing:
                    return {"status": "duplicate"}

            # Find transaction
            payment_id = event_data.get("paymentID") or event_data.get("shopTransactionId")
            if not payment_id:
                error_message = "No payment ID in webhook"
                return {"status": "ignored"}

            stmt = (
                select(PaymentTransaction, TenantPaymentProvider)
                .join(
                    TenantPaymentProvider,
                    and_(
                        TenantPaymentProvider.tenant_id == PaymentTransaction.tenant_id,
                        TenantPaymentProvider.provider == PaymentTransaction.provider,
                    ),
                )
                .where(
                    and_(
                        PaymentTransaction.provider_payment_intent_id == payment_id,
                        PaymentTransaction.provider == "banca_sella",
                    )
                )
            )

            result = self.db.execute(stmt).first()
            if not result:
                error_message = f"Transaction not found for payment {payment_id}"
                return {"status": "ignored"}

            transaction, tenant_provider = result
            transaction_id = str(transaction.id)

            # Verify webhook
            credentials = self.encryption.decrypt(tenant_provider.credentials)
            provider = BancaSellaProvider(
                credentials=credentials,
                mode=tenant_provider.mode,
                config=tenant_provider.config,
            )

            verified_event = await provider.verify_webhook(
                payload=payload if isinstance(payload, bytes) else payload,
                signature=signature,
                headers=headers,
            )

            # Process event
            await self._process_event(
                event_type=verified_event.get("eventType", "payment_update"),
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
            processing_time_ms = int((time.time() - start_time) * 1000)
            webhook_log = PaymentWebhookLog(
                provider="banca_sella",
                event_type=event_type,
                event_id=event_id,
                payload=event_data or {},
                signature=signature,
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
        """Process a Banca Sella webhook event."""
        transaction.webhook_events.append(
            {
                "event_type": event_type,
                "received_at": datetime.utcnow().isoformat(),
                "payment_id": event_data.get("paymentID"),
            }
        )

        # Banca Sella uses TransactionResult: OK, KO, PENDING, XX (cancelled)
        status = event_data.get("TransactionResult", "").upper()

        if status == "OK":
            transaction.status = PaymentStatus.SUCCEEDED.value
            transaction.completed_at = datetime.utcnow()
            transaction.provider_transaction_id = event_data.get("BankTransactionID")
        elif status == "KO":
            transaction.status = PaymentStatus.FAILED.value
            transaction.completed_at = datetime.utcnow()
            transaction.error_message = event_data.get("ErrorDescription", "Payment failed")
        elif status == "XX":
            transaction.status = PaymentStatus.CANCELLED.value
            transaction.completed_at = datetime.utcnow()

        transaction.updated_at = datetime.utcnow()
        self.db.commit()
