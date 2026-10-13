"""The only place indents change status. Views call these; nothing else writes workflow fields."""
from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from rest_framework import serializers

from . import workflow as wf
from .models import Indent, IndentEvent, WorkflowSettings

DATA_FIELDS = sorted(set().union(*wf.STAGE_FIELDS.values()) | wf.REQUEST_FIELDS - {"site", "project", "material"})


class ActionDataSerializer(serializers.ModelSerializer):
    """Types and validates the data fields that can be sent with an action."""
    grn_no = serializers.CharField(max_length=50, required=False, allow_blank=True)
    inspection = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Indent
        fields = DATA_FIELDS + ["grn_no", "inspection"]
        extra_kwargs = {f: {"required": False} for f in DATA_FIELDS}

    def validate(self, attrs):
        for k in ("inv_amount", "inv_gst", "pay_auth_amount", "pay_amount", "rate", "po_rate", "est_rate"):
            if attrs.get(k) is not None and attrs[k] < 0:
                raise serializers.ValidationError({k: "Can’t be negative."})
        return attrs

    def validate_quotes(self, value):
        if not isinstance(value, list) or len(value) > 10:
            raise serializers.ValidationError("Quotes must be a list (max 10).")
        clean = []
        for q in value:
            if not isinstance(q, dict):
                raise serializers.ValidationError("Each quote must be an object.")
            clean.append({k: q.get(k) for k in ("vendor", "rate", "gst", "freight", "delivery_days", "terms") if k in q})
        return clean


def _engine_value(v):
    return float(v) if isinstance(v, Decimal) else v


def next_number(site) -> str:
    today = timezone.localdate()
    prefix = f"IND-{today:%y%m%d}-"
    count = Indent.objects.filter(number__startswith=prefix).count() + 1
    while True:
        candidate = f"{prefix}{count:03d}"
        if not Indent.objects.filter(number=candidate).exists():
            return candidate
        count += 1


@transaction.atomic
def raise_indent(user, validated: dict) -> Indent:
    cfg = WorkflowSettings.load().cfg()
    probe = {"qty": float(validated["qty"]), "est_rate": _engine_value(validated.get("est_rate")),
             "raised_by": user.pk, "history": [{"action": "raise"}]}
    indent = Indent(**validated, raised_by=user, number=next_number(validated["site"]),
                    status="Requested", stage=wf.first_stage(probe, cfg), stage_entered_at=timezone.now())
    for attempt in range(5):          # two people raising at the same moment can draw the same number
        try:
            with transaction.atomic():
                indent.save()
            break
        except IntegrityError:
            if attempt == 4:
                raise
            indent.pk = None
            indent.number = next_number(validated["site"])
    ev = IndentEvent.objects.create(indent=indent, action="raise", stage="raise", to_status=indent.status,
                                    to_stage=indent.stage, by=user)
    _after_commit(indent, ev)
    return indent


@transaction.atomic
def perform_action(indent_id: int, user, action: str, entry: dict, data: dict) -> Indent:
    """Validate and apply one workflow action. Raises wf.WorkflowError or serializers.ValidationError."""
    indent = Indent.objects.select_for_update().get(pk=indent_id)
    cfg = WorkflowSettings.load().cfg()
    who = user.as_who()
    current = indent.as_engine_dict()

    data = data or {}
    allowed = wf.fields_for_action(current, action)
    extra = sorted(set(data) - allowed)
    if extra:
        raise wf.WorkflowError("You can’t change " + ", ".join(extra) + " at this step.")
    ser = ActionDataSerializer(data=data, partial=True)
    ser.is_valid(raise_exception=True)
    clean = {k: v for k, v in ser.validated_data.items() if k in allowed}

    entry = {k: entry.get(k) for k in ("remarks", "qty", "qty_to", "to") if entry.get(k) not in (None, "")}
    for k in ("qty", "qty_to"):
        if k in entry:
            try:
                entry[k] = float(entry[k])
            except (TypeError, ValueError):
                raise wf.WorkflowError("Quantity must be a number.")

    if action == "pay" and clean.get("pay_ref") and IndentEvent.objects.filter(
            indent=indent, action="pay", changes__pay_ref=clean["pay_ref"]).exists():
        raise wf.WorkflowError(f"Payment reference {clean['pay_ref']} is already recorded on this indent — "
                               "it looks like a duplicate payment.")
    t = wf.plan(current, action, entry, {k: _engine_value(v) for k, v in clean.items()}, who, cfg)

    lane = "purchase" if action in wf.PURCHASE_ACTIONS else "indent"
    from_status = indent.pstatus if lane == "purchase" else indent.status
    at_stage = indent.pstage if lane == "purchase" else indent.stage
    for k, v in clean.items():
        if k not in ("grn_no", "inspection"):
            setattr(indent, k, v)
    stage_changed = t["stage"] != indent.stage or (t["pstage"] or "") != (indent.pstage or "")
    indent.status, indent.stage = t["status"], t["stage"]
    indent.pstatus, indent.pstage = t["pstatus"] or "", t["pstage"] or ""
    for k, v in t["extra"].items():
        field = Indent._meta.get_field(k)
        if v in (None, ""):
            v = None if field.null else ""
        elif isinstance(field, models.DecimalField):
            v = Decimal(str(v))
        setattr(indent, k, v)
    if action == "approve" and entry.get("qty_to") is not None:
        indent.approved_qty = Decimal(str(entry["qty_to"]))
    now = timezone.now()
    if indent.stage == "closed" and not indent.closed_at:
        indent.closed_at = now
    if indent.pstage == "closed" and not indent.pclosed_at:
        indent.pclosed_at = now
    if stage_changed:
        indent.stage_entered_at = now
    indent.save()
    _post_stock(indent, action, entry, clean, user)

    ev = IndentEvent.objects.create(
        indent=indent, action=action, lane=lane, stage=at_stage, from_status=from_status,
        to_status=indent.pstatus if lane == "purchase" else indent.status,
        to_stage=indent.pstage if lane == "purchase" else indent.stage, by=user,
        remarks=entry.get("remarks", ""), sent_to=entry.get("to", ""),
        qty=Decimal(str(entry["qty"])) if "qty" in entry else None,
        qty_to=Decimal(str(entry["qty_to"])) if "qty_to" in entry else None,
        grn_no=clean.get("grn_no", ""), inspection=clean.get("inspection", ""),
        changes={k: str(v) if not isinstance(v, (list, dict, int, float, bool, type(None))) else v
                 for k, v in clean.items()},
        override=bool(t.get("override")),
    )
    if ev.override:
        from apps.audit.log import record
        record("indent.override", actor=user, target=indent,
               summary=f"Administrator override on {indent.number}: {wf.ACTION_LABEL.get(action, action)} at "
                       f"{wf.STAGE[at_stage].short if at_stage in wf.STAGE else at_stage}",
               changes={"action": action, "step": at_stage, "remarks": ev.remarks})
    _after_commit(indent, ev)
    return indent


@transaction.atomic
def edit_request(indent_id: int, user, validated: dict) -> Indent:
    indent = Indent.objects.select_for_update().get(pk=indent_id)
    cfg = WorkflowSettings.load().cfg()
    if not wf.can_edit_request(indent.as_engine_dict(), user.as_who(), cfg):
        raise wf.WorkflowError("Only the person who raised the indent can edit it, and only before it is approved.")
    for k, v in validated.items():
        setattr(indent, k, v)
    indent.save()
    IndentEvent.objects.create(indent=indent, action="edit", stage=indent.stage, by=user, to_status=indent.status,
                               to_stage=indent.stage,
                               changes={k: str(v) if not isinstance(v, (int, float, type(None))) else v
                                        for k, v in validated.items()})
    return indent


def _post_stock(indent, action, entry, clean, user):
    """Indents linked to a catalogue item move the site store's stock automatically:
    issue from stock → OUT, receive (GRN) → IN, issue & close → OUT of what was received."""
    if not indent.material_id or action not in ("issue", "receive", "issueClose"):
        return
    from apps.materials.services import StockError, post_entry
    common = dict(site=indent.site, material=indent.material, by=user, indent=indent, project=indent.project)
    try:
        if action == "issue":
            post_entry(kind="OUT", qty=entry["qty"], source="indent-issue", ref=indent.number,
                       party=indent.issued_to or indent.raised_by.name, note="Issued from stock", **common)
        elif action == "receive":
            post_entry(kind="IN", qty=entry["qty"], source="purchase", ref=clean.get("grn_no") or indent.po_no,
                       rate=indent.po_rate or indent.rate, party=indent.po_vendor, note=clean.get("inspection", ""), **common)
        elif action == "issueClose" and indent.received_qty:
            post_entry(kind="OUT", qty=indent.received_qty, source="indent-issue", ref=indent.number,
                       party=indent.issued_to or indent.raised_by.name, note="Issued to site on closing", **common)
    except StockError as e:
        raise wf.WorkflowError(str(e))   # rolls back the whole action


def _after_commit(indent, ev):
    from apps.alerts.tasks import indent_changed
    transaction.on_commit(lambda: indent_changed.delay(indent.pk, ev.pk))
