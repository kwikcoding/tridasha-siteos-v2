"""Attachments shared by every module (DPR photos, bill copies, closure evidence, drawings)."""
import os
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".xlsx", ".xls", ".csv", ".docx", ".doc", ".dwg",
               ".dxf", ".zip", ".txt"}
MAX_BYTES = 20 * 1024 * 1024


def upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"uploads/{instance.content_type.model}/{uuid.uuid4().hex}{ext}"


class Attachment(models.Model):
    """A file kept for a record. Files are never replaced or deleted through the app — add a new one instead.
    They are served only through the API, after the same permission check as the record they belong to."""
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    record = GenericForeignKey("content_type", "object_id")
    file = models.FileField(upload_to=upload_to)
    name = models.CharField(max_length=200)
    size = models.PositiveIntegerField(default=0)
    purpose = models.CharField(max_length=30, blank=True)     # e.g. "evidence", "bill", "photo"
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def as_dict(self, base):
        return {"id": self.id, "name": self.name, "size": self.size, "purpose": self.purpose,
                "uploaded_by": self.uploaded_by.name, "uploaded_at": self.uploaded_at,
                "url": f"{base}attachments/{self.id}/"}
