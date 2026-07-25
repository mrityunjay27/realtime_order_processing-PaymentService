from django.db import models


class ProcessedEvent(models.Model):
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processed_events"

    def __str__(self):
        return f"{self.event_type} [{self.event_id}]"
