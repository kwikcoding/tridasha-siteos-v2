from datetime import datetime

from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin, module_permission

from . import services
from . import workflow as wf
from .models import Indent, IndentEvent, WorkflowSettings
from .serializers import ActionSerializer, IndentCreateSerializer, IndentDetailSerializer, IndentListSerializer

TABS = ["queue", "open", "purchases", "raised", "closed", "rejected", "all"]


def _wf_error(e):
    return ValidationError({"detail": str(e)})


class IndentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                    mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Indents. Status only moves through POST /indents/{id}/act/."""
    permission_classes = [permissions.IsAuthenticated,
                          module_permission("indents", act="indents.view", export="indents.export")]
    search_fields = ["number", "item", "item_code", "po_no", "po_vendor", "purpose"]
    filterset_fields = ["site", "status", "stage", "pstage", "priority"]
    ordering_fields = ["created_at", "need_by", "number", "stage_entered_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        u = self.request.user
        qs = Indent.objects.select_related("site", "raised_by").prefetch_related(
            Prefetch("history", queryset=IndentEvent.objects.select_related("by")))
        if not u.all_sites:
            qs = qs.filter(Q(site__in=u.site_ids()) | Q(raised_by=u))
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return IndentCreateSerializer
        if self.action in ("retrieve", "partial_update", "act"):
            return IndentDetailSerializer
        return IndentListSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.user.is_authenticated:
            ctx["who"] = self.request.user.as_who()
            ctx["cfg"] = WorkflowSettings.load().cfg()
        return ctx

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        tab = request.query_params.get("tab", "all")
        final = list(wf.FINAL)
        if tab == "open":
            qs = qs.exclude(status__in=final)
        elif tab == "closed":
            qs = qs.filter(status__in=["Closed", "Stock Issued"])
        elif tab == "rejected":
            qs = qs.filter(status__in=["Rejected", "Cancelled"])
        elif tab == "raised":
            qs = qs.filter(raised_by=request.user)
        elif tab == "purchases":
            qs = qs.exclude(pstage="").exclude(pstage="closed")
        elif tab == "queue":
            # "waiting for me" — decided by the workflow engine, so it always matches the buttons
            ctx = self.get_serializer_context()
            candidates = qs.exclude(status__in=final, pstage__in=["", "closed"])
            ids = [i.pk for i in candidates
                   if wf.allowed_actions(i.as_engine_dict([{"action": e.action, "by": e.by_id} for e in i.history.all()]),
                                         ctx["who"], ctx["cfg"])]
            qs = qs.filter(pk__in=ids)
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page if page is not None else qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    def create(self, request, *args, **kwargs):
        ser = IndentCreateSerializer(data=request.data, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        indent = services.raise_indent(request.user, ser.validated_data)
        return Response(self._detail(indent.pk), status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        indent = self.get_object()
        ser = IndentCreateSerializer(indent, data=request.data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        try:
            services.edit_request(indent.pk, request.user, ser.validated_data)
        except wf.WorkflowError as e:
            raise _wf_error(e)
        return Response(self._detail(indent.pk))

    def update(self, request, *args, **kwargs):
        return Response({"detail": "Use PATCH."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"])
    def act(self, request, pk=None):
        indent = self.get_object()      # also checks the user can see it
        ser = ActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        try:
            services.perform_action(indent.pk, request.user, v["action"], v, v.get("data") or {})
        except wf.WorkflowError as e:
            raise _wf_error(e)
        return Response(self._detail(indent.pk))

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        """Excel download of the indents the user can see (respects ?tab= and filters)."""
        qs = self.filter_queryset(self.get_queryset())
        wb = Workbook()
        ws = wb.active
        ws.title = "Indents"
        cols = ["number", "site", "item", "unit", "qty", "approved_qty", "issued_qty", "purchase_qty", "received_qty",
                "status", "stage", "pstatus", "need_by", "priority", "raised_by", "po_no", "po_vendor", "po_rate",
                "po_expected", "inv_no", "inv_amount", "paid_on", "created_at", "closed_at"]
        ws.append([c.replace("_", " ").title() for c in cols])
        for i in qs:
            row = []
            for c in cols:
                v = getattr(i, c)
                if c == "site":
                    v = i.site.name
                elif c == "raised_by":
                    v = i.raised_by.name
                elif isinstance(v, datetime) and timezone.is_aware(v):
                    v = timezone.localtime(v).replace(tzinfo=None)
                row.append(v)
            ws.append(row)
        resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="indents-{timezone.localdate()}.xlsx"'
        wb.save(resp)
        return resp

    def _detail(self, pk):
        obj = self.get_queryset().get(pk=pk)
        return IndentDetailSerializer(obj, context=self.get_serializer_context()).data


def _meta_payload():
    cfg = WorkflowSettings.load()
    return {
        "stages": [{"n": s.n, "key": s.key, "lane": s.lane, "label": s.label, "short": s.short, "dept": s.dept,
                    "actions": list(s.actions), "approve_label": s.approve_label, "required": s.required, "pseudo": s.pseudo, "can_qty": s.can_qty}
                   for s in wf.STAGES],
        "action_labels": wf.ACTION_LABEL,
        "button_labels": wf.BUTTON_LABEL,
        "needs_remark": sorted(wf.NEEDS_REMARK),
        "settings": {"stages": cfg.stages, "mgmt_limit": cfg.mgmt_limit, "mgmt_never": cfg.mgmt_never},
    }


@api_view(["GET"])
def workflow_meta(request):
    """Static description of the 12 steps for the frontend (labels, actions, which need remarks)."""
    return Response(_meta_payload())


@api_view(["PUT"])
@permission_classes([permissions.IsAuthenticated, IsAdmin])
def workflow_settings(request):
    from apps.audit.log import record
    obj = WorkflowSettings.load()
    before = {"stages": obj.stages, "mgmt_limit": str(obj.mgmt_limit), "mgmt_never": obj.mgmt_never}
    stages = request.data.get("stages") or {}
    if not isinstance(stages, dict) or any(k not in wf.STAGE for k in stages):
        raise ValidationError({"stages": "Unknown step."})
    obj.stages = {k: {"on": bool(v.get("on", True))} for k, v in stages.items()
                  if isinstance(v, dict) and not wf.STAGE[k].required}
    try:
        obj.mgmt_limit = max(float(request.data.get("mgmt_limit") or 0), 0)
    except (TypeError, ValueError):
        raise ValidationError({"mgmt_limit": "Enter an amount."})
    obj.mgmt_never = bool(request.data.get("mgmt_never"))
    obj.save()
    record("workflow.settings", actor=request.user, summary="Workflow settings changed", request=request,
           changes={"before": before, "after": {"stages": obj.stages, "mgmt_limit": str(obj.mgmt_limit),
                                                "mgmt_never": obj.mgmt_never}})
    return Response(_meta_payload())
