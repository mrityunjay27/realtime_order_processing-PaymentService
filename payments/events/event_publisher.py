from payments.events.kafka_publisher import KafkaEventPublisher
from payments.events.payment_events import (
    PAYMENT_SUCCEEDED,
    PAYMENT_FAILED,
)

publisher = KafkaEventPublisher()


def publish_payment_succeeded(correlation_id, order_id, payment_id, transaction_reference):
    publisher.publish(
        PAYMENT_SUCCEEDED,
        {
            "correlation_id": correlation_id,
            "order_id": order_id,
            "payment_id": payment_id,
            "transaction_reference": transaction_reference,
        },
    )


def publish_payment_failed(correlation_id, order_id, payment_id, reason):
    publisher.publish(
        PAYMENT_FAILED,
        {
            "correlation_id": correlation_id,
            "order_id": order_id,
            "payment_id": payment_id,
            "reason": reason,
        },
    )
