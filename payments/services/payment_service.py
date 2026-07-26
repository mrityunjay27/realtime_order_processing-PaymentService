import logging
from uuid import uuid4

from django.db import transaction, DatabaseError

from payments.models import Payment
from payments.events.event_envelope import EventEnvelope
from payments.events.payment_events import PAYMENT_SUCCEEDED, PAYMENT_FAILED
from payments.events.outbox_service import OutboxService
from payments.events.audit.services import EventHistoryService
from payments.events.audit.constants import AGGREGATE_PAYMENT, format_aggregate_id
from payments.events.exceptions import (
    RetryableEventException,
    NonRetryableEventException,
)

logger = logging.getLogger(__name__)


class PaymentService:

    @staticmethod
    @transaction.atomic
    def process_payment(correlation_id: str, order_id: str, amount: float):
        import random
        import uuid

        payment = Payment.objects.create(
            order_id=order_id,
            amount=amount,
            status="PENDING",
        )

        try:
            # Simulate payment processing: 80% success, 20% failure
            if random.random() < 0.8:
                transaction_reference = str(uuid.uuid4())
                payment.status = "SUCCESS"
                payment.transaction_reference = transaction_reference
                payment.save()

                _publish_payment_succeeded(
                    correlation_id, order_id, str(payment.id), transaction_reference
                )

                logger.info(
                    "Payment %s succeeded for order %s", payment.id, order_id
                )
                return True
            else:
                payment.status = "FAILED"
                payment.save()

                _publish_payment_failed(
                    correlation_id, order_id, str(payment.id), "PAYMENT_DECLINED"
                )

                logger.warning(
                    "Payment %s failed for order %s", payment.id, order_id
                )
                return False

        except DatabaseError as exc:
            raise RetryableEventException(
                f"Database error while processing payment: {exc}"
            ) from exc


def _publish_payment_succeeded(correlation_id, order_id, payment_id, transaction_reference):
    envelope = EventEnvelope(
        event_type=PAYMENT_SUCCEEDED,
        correlation_id=correlation_id,
        payload={
            "correlation_id": correlation_id,
            "order_id": order_id,
            "payment_id": payment_id,
            "transaction_reference": transaction_reference,
        },
    )
    OutboxService.create_event(
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        payload=envelope.to_dict(),
    )
    EventHistoryService.record_published(
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        correlation_id=correlation_id,
        aggregate_type=AGGREGATE_PAYMENT,
        aggregate_id=format_aggregate_id(AGGREGATE_PAYMENT, order_id),
        payload=envelope.to_dict(),
    )


def _publish_payment_failed(correlation_id, order_id, payment_id, reason):
    envelope = EventEnvelope(
        event_type=PAYMENT_FAILED,
        correlation_id=correlation_id,
        payload={
            "correlation_id": correlation_id,
            "order_id": order_id,
            "payment_id": payment_id,
            "reason": reason,
        },
    )
    OutboxService.create_event(
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        payload=envelope.to_dict(),
    )
    EventHistoryService.record_published(
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        correlation_id=correlation_id,
        aggregate_type=AGGREGATE_PAYMENT,
        aggregate_id=format_aggregate_id(AGGREGATE_PAYMENT, order_id),
        payload=envelope.to_dict(),
    )
