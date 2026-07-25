from django.core.management.base import BaseCommand
from payments.events.kafka_consumer import KafkaEventConsumer


# python manage.py consume_events
# We have to start this to start consuming events from Kafka. This command will run indefinitely until manually stopped.
# But in production, it can be dockererized.
# payment_consumer:
#   build: ./payment_service
#   command: python manage.py consume_events
#   depends_on:
#     - kafka
#     - postgres

class Command(BaseCommand):
    help = "Start Payment Kafka Consumer"

    def handle(self, *args, **kwargs):

        consumer = KafkaEventConsumer()
        consumer.start()
