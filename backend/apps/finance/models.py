"""Site expenses and contractor / supplier bills: submit → approve (amount) → pay (in parts) — never more than approved."""
from decimal import Decimal

from django.conf import settings
from django.db import models

USER = settings.AUTH_USER_MODEL
MONEY = dict(max_digits=14, decimal_places=2)
CATEGORIES = ["Labour contractor bill", "Material purchase", "Equipment hire", "Fuel", "Transport", "Site petty cash",
              "Utilities", "Professional fees", "Statutory & permits", "Safety", "Repairs & maintenance", "Other"]


class Expense(models.Model):
    STATUS = [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("part_paid", "Part paid"),
              ("paid", "Paid"), ("rejected", "Rejected")]

    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="expenses")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses")
    indent = models.ForeignKey("indents.Indent", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses")
    date = models.DateField(db_index=True)
    category = models.CharField(max_length=40, choices=[(c, c) for c in CATEGORIES], db_index=True)
    description = models.CharField(max_length=300)
    payee = models.CharField(max_length=150)
    bill_no = models.CharField(max_length=60, blank=True)
    amount = models.DecimalField(**MONEY)                       # before GST
    gst = models.DecimalField(**MONEY, default=Decimal("0"))
    status = models.CharField(max_length=10, choices=STATUS, default="draft", db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_amount = models.DecimalField(**MONEY, null=True, blank=True)
    approved_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    paid_total = models.DecimalField(**MONEY, default=Decimal("0"))
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.payee} {self.bill_no or ''} ₹{self.total}".strip()

    @property
    def total(self):
        return (self.amount or 0) + (self.gst or 0)

    @property
    def outstanding(self):
        if self.approved_amount is None:
            return Decimal("0")
        return max(self.approved_amount - self.paid_total, Decimal("0"))

    @property
    def editable(self):
        return self.status in ("draft", "rejected")


class ExpensePayment(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name="payments")
    date = models.DateField()
    amount = models.DecimalField(**MONEY)
    mode = models.CharField(max_length=30, blank=True)          # NEFT, RTGS, cheque, cash, UPI
    ref = models.CharField(max_length=80, blank=True)           # UTR / cheque no
    by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]
        constraints = [models.UniqueConstraint(fields=["expense", "ref"], condition=~models.Q(ref=""),
                                               name="payment_ref_once_per_expense")]
