from django.conf import settings
from django.db import models
from django.utils import timezone

USER = settings.AUTH_USER_MODEL


class Observation(models.Model):
    """Quality inspections, safety observations, incidents and NCRs, with corrective action and closure."""
    KIND = [("inspection", "Quality inspection"), ("safety", "Safety observation"), ("incident", "Safety incident"),
            ("ncr", "NCR — non-conformance"), ("near_miss", "Near miss")]
    SEVERITY = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")]
    STATUS = [("open", "Open"), ("in_progress", "In progress"), ("closed", "Closed")]
    # these always need a photo / document as closure evidence
    EVIDENCE_KINDS = {"ncr", "incident"}
    EVIDENCE_SEVERITY = {"high", "critical"}

    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="observations")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="observations")
    kind = models.CharField(max_length=12, choices=KIND, db_index=True)
    ref_no = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=150, blank=True)
    date = models.DateField(default=timezone.localdate, db_index=True)
    severity = models.CharField(max_length=10, choices=SEVERITY, default="medium")
    assigned_to = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="observations")
    due_date = models.DateField(null=True, blank=True)
    corrective_action = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="open", db_index=True)
    closure_note = models.TextField(blank=True)
    closed_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.ref_no} {self.title}"

    @property
    def needs_evidence(self):
        return self.kind in self.EVIDENCE_KINDS or self.severity in self.EVIDENCE_SEVERITY

    @property
    def overdue(self):
        return bool(self.due_date and self.status != "closed" and self.due_date < timezone.localdate())


class Document(models.Model):
    """A drawing or document. Files are kept as revisions — a new upload never replaces an old one."""
    CATEGORY = [("drawing", "Drawing"), ("specification", "Specification"), ("contract", "Contract / agreement"),
                ("approval", "Statutory approval"), ("report", "Report / test certificate"), ("method", "Method statement"),
                ("other", "Other")]
    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="documents")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="documents")
    category = models.CharField(max_length=15, choices=CATEGORY, db_index=True)
    number = models.CharField(max_length=60)              # drawing / document number
    title = models.CharField(max_length=200)
    discipline = models.CharField(max_length=60, blank=True)   # architectural, structural, MEP …
    archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["site__name", "category", "number"]
        constraints = [models.UniqueConstraint(fields=["site", "number"], name="doc_number_per_site")]

    def __str__(self):
        return f"{self.number} {self.title}"


def rev_upload_to(instance, filename):
    import os
    import uuid
    return f"documents/{instance.document.site_id}/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


class DocumentRevision(models.Model):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="revisions")
    rev = models.CharField(max_length=10)                 # R0, R1 … (or the drawing's own A, B, C)
    file = models.FileField(upload_to=rev_upload_to)
    file_name = models.CharField(max_length=200)
    size = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=300, blank=True)   # what changed
    status = models.CharField(max_length=20, default="For construction",
                              choices=[(x, x) for x in ["For information", "For approval", "For construction", "Superseded"]])
    uploaded_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "-uploaded_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["document", "rev"], name="rev_once_per_document")]
