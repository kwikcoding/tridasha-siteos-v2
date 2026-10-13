from django.conf import settings
from django.db import models


class Notification(models.Model):
    """In-app bell item. One row per person per alert; delivery to WhatsApp/email/SMS is recorded on it."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30)              # waiting | returned | closed | overdue | digest
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True)  # frontend path, e.g. /indents/12
    indent = models.ForeignKey("indents.Indent", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    dedupe_key = models.CharField(max_length=120, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    delivered = models.JSONField(default=dict, blank=True)   # {"whatsapp": "ok" | "error: …", "email": …, "sms": …}

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]
