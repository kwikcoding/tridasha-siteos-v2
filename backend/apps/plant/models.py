"""Plant & equipment register: allocation to sites/projects, maintenance and breakdowns."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

USER = settings.AUTH_USER_MODEL
MONEY = dict(max_digits=14, decimal_places=2)


class Equipment(models.Model):
    STATUS = [("available", "Available"), ("in_use", "In use"), ("maintenance", "Under maintenance"),
              ("breakdown", "Breakdown"), ("disposed", "Disposed / returned")]
    OWNERSHIP = [("owned", "Owned"), ("hired", "Hired")]

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=60, blank=True)        # excavator, mixer, crane, DG set, vibrator …
    make_model = models.CharField(max_length=120, blank=True)
    reg_no = models.CharField(max_length=40, blank=True)
    ownership = models.CharField(max_length=6, choices=OWNERSHIP, default="owned")
    hire_rate = models.DecimalField(**MONEY, null=True, blank=True)   # per day, when hired
    supplier = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="available", db_index=True)
    site = models.ForeignKey("sites.Site", null=True, blank=True, on_delete=models.PROTECT, related_name="equipment")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="equipment")
    service_every_days = models.PositiveIntegerField(null=True, blank=True)
    next_service_due = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "equipment"

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def service_overdue(self):
        return bool(self.next_service_due and self.status != "disposed" and self.next_service_due < timezone.localdate())


class Allocation(models.Model):
    """Where the equipment was, from when to when. Only one open allocation at a time."""
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="allocations")
    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="allocations")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    from_date = models.DateField()
    to_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-from_date", "-id"]
        constraints = [models.UniqueConstraint(fields=["equipment"], condition=Q(to_date__isnull=True),
                                               name="one_open_allocation")]

    def days_in(self, start, end):
        """Calendar days of this allocation inside [start, end]."""
        a, b = max(self.from_date, start), min(self.to_date or end, end)
        return max((b - a).days + 1, 0)


class MaintenanceLog(models.Model):
    KIND = [("service", "Scheduled service"), ("repair", "Repair"), ("breakdown", "Breakdown"), ("inspection", "Inspection")]
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="maintenance")
    date = models.DateField()
    kind = models.CharField(max_length=10, choices=KIND)
    description = models.TextField()
    cost = models.DecimalField(**MONEY, default=Decimal("0"))
    downtime_hours = models.DecimalField(max_digits=7, decimal_places=1, default=Decimal("0"))
    done_by = models.CharField(max_length=120, blank=True)
    by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
