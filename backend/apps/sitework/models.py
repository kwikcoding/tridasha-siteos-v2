"""Tasks & schedule, daily progress reports, labour & attendance."""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

USER = settings.AUTH_USER_MODEL
QTY = dict(max_digits=14, decimal_places=3)
MONEY = dict(max_digits=14, decimal_places=2)


class Task(models.Model):
    STATUS = [("todo", "To do"), ("in_progress", "In progress"), ("blocked", "Blocked"), ("done", "Done"),
              ("cancelled", "Cancelled")]
    PRIORITY = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("critical", "Critical")]
    CLOSED = ("done", "cancelled")

    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="tasks")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks_assigned")
    priority = models.CharField(max_length=10, choices=PRIORITY, default="normal")
    status = models.CharField(max_length=12, choices=STATUS, default="todo", db_index=True)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)      # %
    depends_on = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="dependents")
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_date", "id"]

    def __str__(self):
        return self.title

    @property
    def overdue(self):
        return bool(self.due_date and self.status not in self.CLOSED and self.due_date < timezone.localdate())

    @property
    def days_overdue(self):
        return (timezone.localdate() - self.due_date).days if self.overdue else 0


class DailyReport(models.Model):
    """One report per site (and project) per day. Draft → Submitted → Approved, or Returned for changes."""
    STATUS = [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("returned", "Returned")]
    WEATHER = [("clear", "Clear"), ("cloudy", "Cloudy"), ("rain", "Rain"), ("heavy_rain", "Heavy rain"), ("hot", "Very hot")]

    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="daily_reports")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="daily_reports")
    date = models.DateField(db_index=True)
    weather = models.CharField(max_length=12, choices=WEATHER, default="clear")
    summary = models.TextField(blank=True)
    work_items = models.JSONField(default=list, blank=True)     # [{activity, location, qty, unit, planned_qty}]
    manpower = models.JSONField(default=list, blank=True)       # [{trade, count}]
    materials_used = models.JSONField(default=list, blank=True)  # [{item, qty, unit}]
    issues = models.TextField(blank=True)
    tomorrow_plan = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft", db_index=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "site__name"]
        constraints = [
            models.UniqueConstraint(fields=["site", "project", "date"], condition=Q(project__isnull=False),
                                    name="one_dpr_per_project_day"),
            models.UniqueConstraint(fields=["site", "date"], condition=Q(project__isnull=True),
                                    name="one_dpr_per_site_day"),
        ]

    def __str__(self):
        return f"DPR {self.site.code} {self.date}"

    @property
    def manpower_total(self):
        return sum(int(m.get("count") or 0) for m in self.manpower or [] if isinstance(m, dict))

    @property
    def editable(self):
        return self.status in ("draft", "returned")


class Worker(models.Model):
    """A labourer or gang member on a site's muster roll (direct or through a labour contractor)."""
    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="workers")
    name = models.CharField(max_length=120)
    worker_code = models.CharField(max_length=30, blank=True)
    trade = models.CharField(max_length=60, blank=True)          # mason, helper, bar bender, carpenter …
    contractor = models.CharField(max_length=120, blank=True)    # blank = departmental labour
    mobile = models.CharField(max_length=15, blank=True)
    daily_wage = models.DecimalField(**MONEY, default=Decimal("0"))
    ot_rate = models.DecimalField(**MONEY, default=Decimal("0"))  # per overtime hour
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["site__name", "contractor", "name"]
        constraints = [models.UniqueConstraint(fields=["site", "worker_code"], condition=~Q(worker_code=""),
                                               name="worker_code_per_site")]

    def __str__(self):
        return self.name


class Attendance(models.Model):
    """One mark per worker per day. Once the day is approved (labour.approve) it can't be changed."""
    STATUS = [("present", "Present"), ("half", "Half day"), ("absent", "Absent"), ("leave", "Leave")]
    DAY_FACTOR = {"present": Decimal("1"), "half": Decimal("0.5"), "absent": Decimal("0"), "leave": Decimal("0")}

    worker = models.ForeignKey(Worker, on_delete=models.PROTECT, related_name="attendance")
    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="attendance")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="attendance")
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=8, choices=STATUS)
    ot_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    wage = models.DecimalField(**MONEY, default=Decimal("0"))     # worked out when marked: day factor × wage + OT
    note = models.CharField(max_length=200, blank=True)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "worker__name"]
        constraints = [models.UniqueConstraint(fields=["worker", "date"], name="one_mark_per_worker_day")]

    def compute_wage(self):
        w = self.worker
        self.wage = (self.DAY_FACTOR[self.status] * w.daily_wage + (self.ot_hours or 0) * w.ot_rate).quantize(Decimal("0.01"))
        return self.wage
