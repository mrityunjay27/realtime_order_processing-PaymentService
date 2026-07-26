import logging

from confluent_kafka import Consumer, KafkaError
from django.conf import settings
from django.db import transaction, IntegrityError

logger = logging.getLogger(__name__)

from payments.events.event_envelope import EventEnvelope
from payments.events.idempotency import IdempotencyService
from payments.events.payment_events import PAYMENT_REQUESTED, PAYMENT_REQUESTED_RETRY
from payments.events.failure_handler import FailureHandler
from payments.events.audit.services import EventHistoryService
from payments.events.audit.constants import AGGREGATE_PAYMENT, format_aggregate_id
from payments.services.payment_service import PaymentService


class KafkaEventConsumer:

    def __init__(self):
        self.consumer = Consumer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group.id": "payment-service-group",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self.failure_handler = FailureHandler(
            retry_topic="payments.requested.retry",
            dlq_topic="payments.requested.dlq",
        )

    def handle_payment_requested(self, envelope: EventEnvelope):
        event = envelope.payload

        logger.info("Received event [%s]: %s", envelope.correlation_id, event)

        PaymentService.process_payment(
            correlation_id=envelope.correlation_id,
            order_id=event["order_id"],
            amount=event["amount"],
        )

    def _extract_aggregate_id(self, envelope: EventEnvelope) -> str:
        return envelope.payload.get("order_id") or "unknown"

    def start(self):
        self.consumer.subscribe([PAYMENT_REQUESTED, PAYMENT_REQUESTED_RETRY])

        logger.info("Payment Consumer Started...")

        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("Consumer error: %s", msg.error())
                    continue

                envelope = EventEnvelope.from_json(msg.value().decode("utf-8"))
                envelope_dict = envelope.to_dict()

                try:
                    with transaction.atomic():
                        if IdempotencyService.already_processed(envelope.event_id):
                            logger.info("Event %s already processed", envelope.event_id)

                        elif envelope.event_type in (PAYMENT_REQUESTED, PAYMENT_REQUESTED_RETRY):
                            self.handle_payment_requested(envelope)
                            IdempotencyService.mark_processed(envelope.event_id, envelope.event_type)

                            aggregate_id = self._extract_aggregate_id(envelope)
                            EventHistoryService.record_consumed(
                                event_id=envelope.event_id,
                                event_type=envelope.event_type,
                                correlation_id=envelope.correlation_id,
                                aggregate_type=AGGREGATE_PAYMENT,
                                aggregate_id=format_aggregate_id(AGGREGATE_PAYMENT, aggregate_id),
                                payload=envelope.to_dict(),
                            )

                        else:
                            logger.warning("No handler for event_type %s", envelope.event_type)

                    # DB transaction succeeded — safe to commit Kafka offset
                    self.consumer.commit(msg)

                except IntegrityError:
                    # Database says duplicate (race condition) — safe to commit
                    logger.info("Duplicate event %s, committing offset", envelope.event_id)
                    self.consumer.commit(msg)

                except Exception as exc:
                    self.consumer.commit(msg)

                    aggregate_id = envelope.payload.get("order_id") or "unknown"
                    EventHistoryService.record_consumed_failed(
                        event_id=envelope.event_id,
                        event_type=envelope.event_type,
                        correlation_id=envelope.correlation_id,
                        aggregate_type=AGGREGATE_PAYMENT,
                        aggregate_id=format_aggregate_id(AGGREGATE_PAYMENT, aggregate_id),
                        payload=envelope.to_dict(),
                    )

                    self.failure_handler.handle(envelope_dict, exc)

        except KeyboardInterrupt:
            pass
        finally:
            self.consumer.close()
