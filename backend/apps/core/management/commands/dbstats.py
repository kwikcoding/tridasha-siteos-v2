"""Fingerprint of the data — row counts per table and key totals — to compare a restored copy with the original.

    python manage.py dbstats            # prints JSON
"""
import hashlib
import json

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db.models import Sum


class Command(BaseCommand):
    help = "Row counts and money / stock totals, as JSON (for backup-restore checks)."

    def handle(self, *args, **opts):
        out = {"counts": {}, "totals": {}}
        for m in apps.get_models():
            if m._meta.app_label in ("contenttypes", "sessions", "admin"):
                continue
            out["counts"][m._meta.label] = m.objects.count()
        q = lambda label, field: str(apps.get_model(label).objects.aggregate(s=Sum(field))["s"] or 0)  # noqa: E731
        out["totals"] = {
            "indent_paid": q("indents.Indent", "paid_total"), "expense_paid": q("finance.Expense", "paid_total"),
            "expense_approved": q("finance.Expense", "approved_amount"), "wages": q("sitework.Attendance", "wage"),
            "stock_in": str(apps.get_model("materials.StockEntry").objects.filter(kind="IN").aggregate(s=Sum("qty"))["s"] or 0),
            "stock_out": str(apps.get_model("materials.StockEntry").objects.filter(kind="OUT").aggregate(s=Sum("qty"))["s"] or 0),
        }
        names = apps.get_model("core.Attachment").objects.order_by("id").values_list("file", flat=True)
        out["attachment_paths_sha"] = hashlib.sha256("\n".join(names).encode()).hexdigest()
        self.stdout.write(json.dumps(out, sort_keys=True, indent=1))
