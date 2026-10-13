from rest_framework import serializers

from apps.core.scoped import SiteProjectSerializer

from .models import Expense, ExpensePayment


class PaymentSerializer(serializers.ModelSerializer):
    by_name = serializers.CharField(source="by.name", read_only=True)

    class Meta:
        model = ExpensePayment
        fields = ["id", "date", "amount", "mode", "ref", "by_name", "at"]


class ExpenseSerializer(SiteProjectSerializer):
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    editable = serializers.BooleanField(read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.name", read_only=True, default="")
    indent_number = serializers.CharField(source="indent.number", read_only=True, default="")
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Expense
        fields = ["id", "site", "site_name", "project", "project_name", "indent", "indent_number", "date", "category",
                  "description", "payee", "bill_no", "amount", "gst", "total", "status", "editable", "submitted_at",
                  "approved_amount", "approved_by_name", "approved_at", "review_note", "paid_total", "outstanding",
                  "payments", "created_by", "created_by_name", "created_at"]
        read_only_fields = ["status", "submitted_at", "approved_amount", "approved_at", "review_note", "paid_total",
                            "created_by"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and not self.instance.editable:
            raise serializers.ValidationError("This bill is submitted — it can’t be changed now.")
        for k in ("amount", "gst"):
            if attrs.get(k) is not None and attrs[k] < 0:
                raise serializers.ValidationError({k: "Can’t be negative."})
        if attrs.get("amount") is not None and attrs["amount"] == 0:
            raise serializers.ValidationError({"amount": "Enter the amount."})
        site = attrs.get("site", getattr(self.instance, "site", None))
        ind = attrs.get("indent", getattr(self.instance, "indent", None))
        if ind is not None and ind.site_id != site.pk:
            raise serializers.ValidationError({"indent": "That indent is for another site."})
        payee = (attrs.get("payee", getattr(self.instance, "payee", "")) or "").strip()
        bill = (attrs.get("bill_no", getattr(self.instance, "bill_no", "")) or "").strip()
        if bill:
            dup = Expense.objects.filter(payee__iexact=payee, bill_no__iexact=bill).exclude(status="rejected")
            if self.instance is not None:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise serializers.ValidationError({"bill_no": f"Bill {bill} from {payee} is already entered."})
        return attrs


class PaySerializer(serializers.Serializer):
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    mode = serializers.CharField(required=False, allow_blank=True, max_length=30)
    ref = serializers.CharField(required=False, allow_blank=True, max_length=80)
