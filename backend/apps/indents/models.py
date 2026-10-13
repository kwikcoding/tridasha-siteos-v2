from decimal import Decimal

from django.conf import settings
from django.db import models

from . import workflow as wf

QTY = dict(max_digits=14, decimal_places=3, null=True, blank=True)
MONEY = dict(max_digits=14, decimal_places=2, null=True, blank=True)


class WorkflowSettings(models.Model):
    """Single row: which optional steps are on, and the management approval limit."""
    stages = models.JSONField(default=dict, blank=True)          # {stage_key: {"on": bool}}
    mgmt_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)   # 0 = every indent
    mgmt_never = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "workflow settings"

    @classmethod
    def load(cls) -> "WorkflowSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def cfg(self) -> wf.Config:
        return wf.config({"stages": self.stages, "mgmt_limit": "never" if self.mgmt_never else float(self.mgmt_limit)})


class Indent(models.Model):
    PRIORITY = [("normal", "Normal"), ("urgent", "Urgent"), ("critical", "Critical")]

    number = models.CharField(max_length=30, unique=True)
    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="indents")
    # 01 — the request
    material = models.ForeignKey("materials.Material", null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="indents")
    item = models.CharField(max_length=200)
    item_code = models.CharField(max_length=50, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    need_by = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY, default="normal")
    purpose = models.TextField(blank=True)
    est_rate = models.DecimalField(**MONEY)
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="indents_raised")

    # workflow pointers (only ever changed through services.perform_action)
    status = models.CharField(max_length=40, default="Requested", db_index=True)
    stage = models.CharField(max_length=20, db_index=True)
    pstatus = models.CharField(max_length=40, blank=True)
    pstage = models.CharField(max_length=20, blank=True, db_index=True)
    stage_entered_at = models.DateTimeField(null=True, blank=True)
    held_from = models.CharField(max_length=40, blank=True)
    close_reason = models.CharField(max_length=200, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    pclosed_at = models.DateTimeField(null=True, blank=True)

    # quantities
    approved_qty = models.DecimalField(**QTY)
    issued_qty = models.DecimalField(**QTY)
    purchase_qty = models.DecimalField(**QTY)
    received_qty = models.DecimalField(**QTY)
    balance_cancelled = models.DecimalField(**QTY)

    # 02 stock / 03 tech / 04 mgmt
    stock_note = models.TextField(blank=True)
    stock_seen = models.DecimalField(**QTY)
    spec_note = models.TextField(blank=True)
    boq_ref = models.CharField(max_length=100, blank=True)
    budget_note = models.TextField(blank=True)
    # 05 rfq / 06 vendor
    quotes = models.JSONField(default=list, blank=True)        # [{vendor, rate, gst, freight, delivery_days, terms}]
    purchase_note = models.TextField(blank=True)
    vendor_final = models.CharField(max_length=150, blank=True)
    rate = models.DecimalField(**MONEY)
    lead_days = models.PositiveIntegerField(null=True, blank=True)
    vendor_note = models.TextField(blank=True)
    # 07 po / 08 track
    po_no = models.CharField(max_length=50, blank=True)
    po_date = models.DateField(null=True, blank=True)
    po_vendor = models.CharField(max_length=150, blank=True)
    po_rate = models.DecimalField(**MONEY)
    po_expected = models.DateField(null=True, blank=True)
    tracking = models.TextField(blank=True)
    # 10 issue
    issued_to = models.CharField(max_length=150, blank=True)
    # 11 invoice / 12 payment
    inv_no = models.CharField(max_length=50, blank=True)
    inv_date = models.DateField(null=True, blank=True)
    inv_amount = models.DecimalField(**MONEY)
    inv_gst = models.DecimalField(**MONEY)
    inv_note = models.TextField(blank=True)
    paid_on = models.DateField(null=True, blank=True)
    pay_mode = models.CharField(max_length=30, blank=True)
    pay_ref = models.CharField(max_length=80, blank=True)
    pay_amount = models.DecimalField(**MONEY)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["site", "status"])]

    def __str__(self):
        return f"{self.number} {self.item}"

    ENGINE_FIELDS = ["status", "stage", "pstatus", "pstage", "qty", "approved_qty", "issued_qty", "purchase_qty",
                     "received_qty", "held_from", "rate", "po_rate", "est_rate"]

    def as_engine_dict(self, history=None) -> dict:
        d = {}
        for f in self.ENGINE_FIELDS:
            v = getattr(self, f)
            d[f] = float(v) if isinstance(v, Decimal) else v
        d["raised_by"] = self.raised_by_id
        if history is None:
            history = [{"action": a, "by": b} for a, b in self.history.values_list("action", "by_id")]
        d["history"] = history
        return d


class IndentEvent(models.Model):
    """Append-only history: one row per action. Never edited or deleted through the API."""
    indent = models.ForeignKey(Indent, on_delete=models.CASCADE, related_name="history")
    action = models.CharField(max_length=20)
    lane = models.CharField(max_length=10, default="indent")
    stage = models.CharField(max_length=20, blank=True)      # step the action was taken at
    from_status = models.CharField(max_length=40, blank=True)
    to_status = models.CharField(max_length=40, blank=True)
    to_stage = models.CharField(max_length=20, blank=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True)
    qty = models.DecimalField(**QTY)          # issued / received with this action
    qty_to = models.DecimalField(**QTY)       # approved quantity, when an approver reduces it
    sent_to = models.CharField(max_length=20, blank=True)   # sendback target
    grn_no = models.CharField(max_length=50, blank=True)
    inspection = models.TextField(blank=True)
    changes = models.JSONField(default=dict, blank=True)    # data fields filled in with this action
    override = models.BooleanField(default=False)           # administrator acted outside their own role

    class Meta:
        ordering = ["at", "id"]

    @property
    def label(self):
        return wf.ACTION_LABEL.get(self.action, self.action)
