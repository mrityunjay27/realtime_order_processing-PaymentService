import logging

from payments.models.processed_event import ProcessedEvent

logger = logging.getLogger(__name__)


class IdempotencyService:

    @staticmethod
    def already_processed(event_id: str) -> bool:
        return ProcessedEvent.objects.filter(event_id=event_id).exists()

    @staticmethod
    def mark_processed(event_id: str, event_type: str):
        ProcessedEvent.objects.create(
            event_id=event_id,
            event_type=event_type,
        )
        logger.info("Marked event %s [%s] as processed", event_id, event_type)
