from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Who did what, when. Append-only: nothing in the app edits or deletes these rows."""
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=40, db_index=True)       # e.g. login.success, user.update, indent.override
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["target_type", "target_id"])]
