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


def logo_upload_to(instance, filename):
    return f"company/logo-{uuid.uuid4().hex[:8]}{os.path.splitext(filename)[1].lower()}"


class CompanyProfile(models.Model):
    """One row: the company's own details, used on reports, exports and the app header."""
    MONTHS = [(i, m) for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                            "September", "October", "November", "December"], start=1)]
    name = models.CharField(max_length=150, default="Tridasha")
    legal_name = models.CharField(max_length=200, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    pan = models.CharField(max_length=10, blank=True)
    cin = models.CharField(max_length=21, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    pincode = models.CharField(max_length=6, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    financial_year_start = models.PositiveSmallIntegerField(choices=MONTHS, default=4)
    logo = models.FileField(upload_to=logo_upload_to, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
