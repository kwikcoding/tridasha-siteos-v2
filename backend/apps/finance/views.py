from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.scoped import ScopedViewSet

from .models import CATEGORIES, Expense, ExpensePayment
from .serializers import ExpenseSerializer, PaySerializer


class ExpenseViewSet(ScopedViewSet):
    module = "expenses"
    queryset = Expense.objects.select_related("site", "project", "indent", "created_by", "approved_by") \
        .prefetch_related("payments__by")
    serializer_class = ExpenseSerializer
    audit_label = "bill"
    search_fields = ["payee", "bill_no", "description"]
    extra_codes = {"submit": "expenses.create", "approve": "expenses.approve", "reject": "expenses.approve",
                   "pay": "expenses.edit", "categories": "expenses.view", "summary": "expenses.view",
                   "destroy": "expenses.edit"}
    export_columns = [("Date", "date"), ("Site", "site.name"), ("Project", "project.name"), ("Category", "category"),
                      ("Payee", "payee"), ("Bill no", "bill_no"), ("Description", "description"),
                      ("Amount (₹)", "amount"), ("GST (₹)", "gst"), ("Total (₹)", "total"),
                      ("Approved (₹)", "approved_amount"), ("Paid (₹)", "paid_total"), ("Outstanding (₹)", "outstanding"),
                      ("Status", "get_status_display"), ("Indent", "indent.number"), ("Entered by", "created_by.name")]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("category"):
            qs = qs.filter(category=p["category"])
        return qs

    def _own_or_editor(self, e):
        u = self.request.user
        if e.created_by_id != u.pk and not u.has_code("expenses.edit"):
            raise PermissionDenied("Only the person who entered this bill can change it.")

    def perform_update(self, ser):
        self._own_or_editor(ser.instance)
        super().perform_update(ser)

    def perform_destroy(self, e):
        self._own_or_editor(e)
        if e.status != "draft":
            raise ValidationError({"detail": "Only a draft can be deleted."})
        super().perform_destroy(e)

    @action(detail=False, methods=["get"])
    def categories(self, request):
        return Response(CATEGORIES)

    def _locked(self, pk):
        return Expense.objects.select_for_update().get(pk=self.get_object().pk)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def submit(self, request, pk=None):
        e = self._locked(pk)
        self._own_or_editor(e)
        if not e.editable:
            raise ValidationError({"detail": "This bill is already submitted."})
        e.status, e.submitted_at, e.review_note = "submitted", timezone.now(), ""
        e.save(update_fields=["status", "submitted_at", "review_note"])
        self.log(e, "submit", f"Submitted bill {e}")
        return Response(self.get_serializer(e).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        e = self._locked(pk)
        if e.status != "submitted":
            raise ValidationError({"detail": "Only a submitted bill can be approved."})
        if e.created_by_id == request.user.pk and not request.user.is_admin:
            raise PermissionDenied("You can’t approve a bill you entered.")
        try:
            amt = Decimal(str(request.data.get("approved_amount", e.total)))
        except Exception:
            raise ValidationError({"approved_amount": "Enter the amount being approved."})
        if amt <= 0:
            raise ValidationError({"approved_amount": "Enter the amount being approved."})
        if amt > e.total:
            raise ValidationError({"approved_amount": f"You can’t approve more than the bill (₹{e.total:,.2f})."})
        e.status, e.approved_amount, e.approved_by, e.approved_at = "approved", amt, request.user, timezone.now()
        e.review_note = str(request.data.get("note") or "")[:1000]
        e.save(update_fields=["status", "approved_amount", "approved_by", "approved_at", "review_note"])
        self.log(e, "approve", f"Approved ₹{amt:,.2f} on bill {e}", approved_amount=amt)
        return Response(self.get_serializer(e).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reject(self, request, pk=None):
        e = self._locked(pk)
        if e.status != "submitted":
            raise ValidationError({"detail": "Only a submitted bill can be rejected."})
        note = str(request.data.get("note") or "").strip()
        if not note:
            raise ValidationError({"note": "Say why it’s rejected."})
        e.status, e.review_note = "rejected", note
        e.save(update_fields=["status", "review_note"])
        self.log(e, "reject", f"Rejected bill {e}", note=note)
        return Response(self.get_serializer(e).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def pay(self, request, pk=None):
        e = self._locked(pk)
        if e.status not in ("approved", "part_paid"):
            raise ValidationError({"detail": "Only an approved bill can be paid."})
        if e.approved_by_id == request.user.pk:
            raise PermissionDenied("Whoever approved a bill can’t also pay it.")
        ser = PaySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        if v["amount"] <= 0:
            raise ValidationError({"amount": "Enter the amount paid."})
        if v["amount"] > e.outstanding:
            raise ValidationError({"amount": f"That is more than the ₹{e.outstanding:,.2f} still approved for payment."})
        ref = (v.get("ref") or "").strip()
        if ref and e.payments.filter(ref=ref).exists():
            raise ValidationError({"ref": f"Payment reference {ref} is already recorded on this bill."})
        ExpensePayment.objects.create(expense=e, date=v["date"], amount=v["amount"], mode=v.get("mode", ""), ref=ref,
                                      by=request.user)
        e.paid_total += v["amount"]
        e.status = "paid" if e.paid_total >= e.approved_amount else "part_paid"
        e.save(update_fields=["paid_total", "status"])
        self.log(e, "pay", f"Paid ₹{v['amount']:,.2f} on bill {e}", amount=v["amount"], ref=ref)
        return Response(self.get_serializer(Expense.objects.get(pk=e.pk)).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.filter_queryset(self.get_queryset()).exclude(status="rejected")
        by_cat = list(qs.values("category").annotate(bills=Count("id"), amount=Sum("amount"), gst=Sum("gst"),
                                                     approved=Sum("approved_amount"), paid=Sum("paid_total"))
                      .order_by("category"))
        by_status = list(qs.values("status").annotate(bills=Count("id")).order_by("status"))
        tot = qs.aggregate(amount=Sum("amount"), gst=Sum("gst"), approved=Sum("approved_amount"), paid=Sum("paid_total"))
        return Response({"by_category": by_cat, "by_status": by_status,
                         "totals": {k: v or 0 for k, v in tot.items()},
                         "outstanding": (tot["approved"] or 0) - (tot["paid"] or 0)})
