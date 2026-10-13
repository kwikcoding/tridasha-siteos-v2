from rest_framework import serializers

from . import workflow as wf
from .models import Indent, IndentEvent


class EventSerializer(serializers.ModelSerializer):
    by_name = serializers.CharField(source="by.name", read_only=True)
    label = serializers.CharField(read_only=True)

    class Meta:
        model = IndentEvent
        fields = ["id", "action", "label", "lane", "stage", "from_status", "to_status", "to_stage", "by", "by_name",
                  "at", "remarks", "qty", "qty_to", "sent_to", "grn_no", "inspection", "changes", "override"]


class IndentListSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    raised_by_name = serializers.CharField(source="raised_by.name", read_only=True)
    waiting_with = serializers.SerializerMethodField()
    purchase_with = serializers.SerializerMethodField()
    stage_label = serializers.SerializerMethodField()
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = Indent
        fields = ["id", "number", "site", "site_name", "material", "item", "item_code", "unit", "qty", "approved_qty", "need_by",
                  "priority", "status", "stage", "stage_label", "pstatus", "pstage", "waiting_with", "purchase_with",
                  "raised_by", "raised_by_name", "po_no", "po_vendor", "po_expected", "stage_entered_at",
                  "allowed_actions", "created_at", "updated_at"]

    def _ctx(self):
        return self.context["who"], self.context["cfg"]

    def _engine(self, obj):
        cache = self.context.setdefault("_engine", {})
        if obj.pk not in cache:
            hist = [{"action": e.action, "by": e.by_id} for e in obj.history.all()]   # prefetched
            cache[obj.pk] = obj.as_engine_dict(hist)
        return cache[obj.pk]

    def get_waiting_with(self, obj):
        return wf.waiting_with(self._engine(obj))

    def get_purchase_with(self, obj):
        return wf.purchase_with(self._engine(obj))

    def get_stage_label(self, obj):
        s = wf.STAGE.get(obj.stage)
        return s.short if s else ("Back with requester" if obj.stage == "requester" else obj.stage.title())

    def get_allowed_actions(self, obj):
        who, cfg = self._ctx()
        return wf.allowed_actions(self._engine(obj), who, cfg)


class IndentDetailSerializer(IndentListSerializer):
    history = EventSerializer(many=True, read_only=True)
    stock_at_site = serializers.SerializerMethodField()
    stock_entries = serializers.SerializerMethodField()

    def get_stock_at_site(self, obj):
        if not obj.material_id:
            return None
        from apps.materials.models import StockEntry
        return StockEntry.balance(obj.site_id, obj.material_id)

    def get_stock_entries(self, obj):
        return [{"id": e.id, "date": e.date, "kind": e.kind, "qty": e.qty, "ref": e.ref, "note": e.note}
                for e in obj.stock_entries.all().order_by("date", "id")]
    steps = serializers.SerializerMethodField()
    money = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    action_fields = serializers.SerializerMethodField()

    class Meta(IndentListSerializer.Meta):
        fields = "__all__"   # all model fields + the declared ones above

    def get_steps(self, obj):
        """Tracker: every step that applies to this indent, with done / current / todo."""
        i = self._engine(obj)
        _, cfg = self._ctx()
        events = list(obj.history.all())
        acted = {e.stage for e in events}
        if any(e.action == "receive" for e in events):
            acted.add("receive")   # receipts are recorded while the indent sits at the delivery step
        out = [{"key": "raise", "n": "01", "label": "Raise indent", "state": "done"}]
        for s in wf.stages_for(i, cfg):
            if s.lane == "purchase":
                current = wf.purchase_open(i) and obj.pstage == s.key
            else:
                current = not wf.is_final(i) and (obj.stage == s.key or (s.key == "receive" and obj.stage == "track"))
            if current:
                state = "current"
            elif s.key in acted:
                state = "done"
            else:
                state = "todo"
            out.append({"key": s.key, "n": s.n, "label": s.label, "short": s.short, "dept": s.dept, "lane": s.lane,
                        "state": state})
        return out

    def get_money(self, obj):
        """Steps 11–12 at a glance: PO × GRN, invoice incl. GST, authorised, paid, still to pay."""
        i = {**self._engine(obj)}
        _, cfg = self._ctx()
        exp, diff, ok = wf.invoice_variance(i, cfg)
        return {"expected": exp, "invoice_total": wf.invoice_total(i), "variance": diff if i.get("inv_amount") else None,
                "within_tolerance": ok, "tolerance_pct": cfg.inv_tolerance_pct, "payable": wf.payable(i),
                "authorised": i.get("pay_auth_amount"), "paid": i.get("paid_total") or 0,
                "outstanding": wf.outstanding(i, cfg)}

    def get_can_edit(self, obj):
        who, cfg = self._ctx()
        return wf.can_edit_request(self._engine(obj), who, cfg)

    def get_action_fields(self, obj):
        """For each allowed action, the extra fields the form should show."""
        i = self._engine(obj)
        order = {f: n for n, f in enumerate(wf.FIELD_ORDER)}
        return {a: sorted(wf.fields_for_action(i, a) - wf.REQUEST_FIELDS, key=lambda f: order.get(f, 99))
                for a in self.get_allowed_actions(obj)}


class IndentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indent
        fields = ["site", "material", "item", "item_code", "unit", "qty", "need_by", "priority", "purpose", "est_rate"]
        extra_kwargs = {"item": {"required": False, "allow_blank": True}}

    def validate(self, attrs):
        m = attrs.get("material")
        if m:
            if not m.active:
                raise serializers.ValidationError({"material": "This catalogue item is switched off."})
            attrs["item"] = attrs.get("item") or m.name
            attrs["item_code"] = m.code
            attrs["unit"] = attrs.get("unit") or m.unit
            if attrs.get("est_rate") is None and m.std_rate is not None:
                attrs["est_rate"] = m.std_rate
        elif not (attrs.get("item") or (self.instance and self.instance.item)):
            raise serializers.ValidationError({"item": "Choose a material from the catalogue or type its name."})
        return attrs

    def validate_qty(self, v):
        if v <= 0:
            raise serializers.ValidationError("Enter a quantity.")
        return v

    def validate_site(self, site):
        user = self.context["request"].user
        if not user.all_sites and site.pk not in user.site_ids():
            raise serializers.ValidationError("You aren’t assigned to this site.")
        return site


class ActionSerializer(serializers.Serializer):
    action = serializers.CharField()
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    qty = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    qty_to = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)
    to = serializers.ChoiceField(choices=["requester", "previous"], required=False)
    data = serializers.DictField(required=False)
