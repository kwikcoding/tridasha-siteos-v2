from datetime import datetime

from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import module_permission
from apps.sites.models import Site

from . import importer, services
from .models import Material, RegisterItem, StockEntry
from .serializers import (ImportSerializer, MaterialSerializer, RegisterItemSerializer, StockEntryCreateSerializer,
                          StockEntrySerializer)

QTY = dict(max_digits=14, decimal_places=3)


def xlsx_response(filename: str, title: str, headers: list[str], rows) -> HttpResponse:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for r in rows:
        ws.append([timezone.localtime(v).replace(tzinfo=None) if isinstance(v, datetime) and timezone.is_aware(v) else v
                   for v in r])
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in list(col)[:200])
        ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    resp = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{filename}-{timezone.localdate()}.xlsx"'
    wb.save(resp)
    return resp


def site_for(user, site_id) -> Site:
    try:
        site = Site.objects.get(pk=int(site_id))
    except (Site.DoesNotExist, TypeError, ValueError):
        raise ValidationError({"site": "Choose a site."})
    if not user.all_sites and site.pk not in user.site_ids():
        raise PermissionDenied("You aren’t assigned to this site.")
    return site


class ImportMixin:
    import_kind = ""

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser, FormParser])
    def import_file(self, request):
        """Upload .xlsx / .csv. First call with commit=false shows what will change; then commit=true applies it."""
        ser = ImportSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        f = ser.validated_data["file"]
        if f.size > importer.MAX_BYTES:
            raise ValidationError({"detail": "File is larger than 10 MB."})
        try:
            res = services.run_import(self.import_kind, f.name, f.read(), ser.validated_data["commit"])
        except importer.ImportError_ as e:
            raise ValidationError({"detail": str(e)})
        return Response(res, status=status.HTTP_200_OK)


class MaterialViewSet(ImportMixin, viewsets.ModelViewSet):
    """Material catalogue. ?site=<id> adds that site's stock balance to each item."""
    serializer_class = MaterialSerializer
    permission_classes = [permissions.IsAuthenticated, module_permission("materials")]
    search_fields = ["code", "name", "category", "spec"]
    filterset_fields = ["category", "active"]
    ordering_fields = ["code", "name", "category", "updated_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]
    import_kind = "catalogue"

    def get_permissions(self):
        # indent raisers need to search the catalogue even without the materials module
        if self.action in ("list", "retrieve") and self.request.user.is_authenticated and self.request.user.can_view("indents"):
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        qs = Material.objects.all()
        site = self.request.query_params.get("site")
        if site:
            s = site_for(self.request.user, site)
            qs = qs.annotate(balance=Coalesce(
                Sum(StockEntry.signed_qty("stock_entries__"), filter=Q(stock_entries__site=s)), Value(0), output_field=DecimalField(**QTY)))
        return qs

    @action(detail=False, methods=["get"])
    def categories(self, request):
        cats = (Material.objects.exclude(category="").values("category").annotate(n=Count("id")).order_by("category"))
        return Response([{"name": c["category"], "count": c["n"]} for c in cats])

    @action(detail=False, methods=["get"])
    def export(self, request):
        qs = self.filter_queryset(Material.objects.all())
        return xlsx_response("materials", "Materials", ["Code", "Name", "Category", "Unit", "Specification", "HSN", "GST %",
                                                        "Rate", "Reorder level", "Active"],
                             ([m.code, m.name, m.category, m.unit, m.spec, m.hsn, m.gst_rate, m.std_rate, m.reorder_level,
                               "Yes" if m.active else "No"] for m in qs))


class RegisterViewSet(ImportMixin, viewsets.ModelViewSet):
    """High-rise materials register."""
    queryset = RegisterItem.objects.select_related("material")
    serializer_class = RegisterItemSerializer
    permission_classes = [permissions.IsAuthenticated, module_permission("materials")]
    search_fields = ["item_id", "item", "system", "trade", "make", "vendor", "spec"]
    filterset_fields = ["trade", "applicability", "status", "material"]
    ordering_fields = ["item_id", "trade", "required_by", "updated_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]
    import_kind = "register"

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.filter_queryset(RegisterItem.objects.all())
        return Response({
            "total": qs.count(),
            "applicability": {r["applicability"]: r["n"] for r in qs.values("applicability").annotate(n=Count("id"))},
            "status": {r["status"]: r["n"] for r in qs.values("status").annotate(n=Count("id"))},
            "trades": [{"name": r["trade"], "count": r["n"]} for r in
                       RegisterItem.objects.exclude(trade="").values("trade").annotate(n=Count("id")).order_by("trade")],
            "linked": qs.exclude(material=None).count(),
        })

    @action(detail=False, methods=["get"])
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset())
        heads = ["Item ID", "Trade", "System / section", "Material / equipment item", "Unit", "Specification to confirm",
                 "Applicability", "Block / floor / zone", "Required quantity", "Approved size / grade / rating",
                 "Approved make", "Vendor", "Drawing / BOQ reference", "Procurement status", "Required-by date",
                 "Remarks / package inclusion", "Catalogue code"]
        return xlsx_response("materials-register", "Materials Register", heads, (
            [r.item_id, r.trade, r.system, r.item, r.unit, r.spec, r.applicability, r.zone, r.req_qty, r.grade, r.make,
             r.vendor, r.boq_ref, r.status, r.required_by, r.remarks, r.material.code if r.material else ""] for r in qs))


class StockViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Stock ledger. Entries are never edited or deleted — post an adjustment instead."""
    serializer_class = StockEntrySerializer
    permission_classes = [permissions.IsAuthenticated, module_permission("materials")]
    filterset_fields = {"site": ["exact"], "material": ["exact"], "kind": ["exact"], "source": ["exact"],
                        "date": ["gte", "lte"], "indent": ["exact"]}
    search_fields = ["material__code", "material__name", "ref", "party", "note"]
    parser_classes = [JSONParser]

    def get_queryset(self):
        u = self.request.user
        qs = StockEntry.objects.select_related("site", "material", "by", "indent")
        return qs if u.all_sites else qs.filter(site__in=u.site_ids())

    def create(self, request, *args, **kwargs):
        ser = StockEntryCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        site = site_for(request.user, v["site"])
        try:
            material = Material.objects.get(pk=v["material"])
        except Material.DoesNotExist:
            raise ValidationError({"material": "Unknown material."})
        try:
            e = services.post_entry(site=site, material=material, kind=v["kind"], qty=v["qty"], by=request.user,
                                    source=v["source"], date=v.get("date"), rate=v.get("rate"), ref=v.get("ref", ""),
                                    party=v.get("party", ""), note=v.get("note", ""))
        except services.StockError as err:
            raise ValidationError({"detail": str(err)})
        return Response(StockEntrySerializer(e).data, status=status.HTTP_201_CREATED)

    def _balances(self, site):
        rows = (StockEntry.objects.filter(site=site).values("material").annotate(
            balance=Sum(StockEntry.signed_qty()), last=Max("date"),
            received=Coalesce(Sum("qty", filter=Q(kind="IN")), Value(0), output_field=DecimalField(**QTY)),
            issued=Coalesce(Sum("qty", filter=Q(kind="OUT")), Value(0), output_field=DecimalField(**QTY))))
        mats = Material.objects.in_bulk([r["material"] for r in rows])
        out = []
        for r in rows:
            m = mats[r["material"]]
            low = m.reorder_level is not None and r["balance"] <= m.reorder_level
            out.append({"material": m.pk, "code": m.code, "name": m.name, "category": m.category, "unit": m.unit,
                        "balance": r["balance"], "received": r["received"], "issued": r["issued"], "last_movement": r["last"],
                        "reorder_level": m.reorder_level, "low": low})
        return sorted(out, key=lambda x: x["code"])

    @action(detail=False, methods=["get"])
    def balances(self, request):
        site = site_for(request.user, request.query_params.get("site"))
        data = self._balances(site)
        if request.query_params.get("format_xlsx"):
            return xlsx_response(f"stock-{site.code}", "Stock", ["Code", "Material", "Category", "Unit", "Received", "Issued",
                                                                  "Balance", "Reorder level", "Low", "Last movement"],
                                 ([b["code"], b["name"], b["category"], b["unit"], b["received"], b["issued"], b["balance"],
                                   b["reorder_level"], "Yes" if b["low"] else "", b["last_movement"]] for b in data))
        return Response(data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        qs = self.filter_queryset(self.get_queryset())[:50000]
        return xlsx_response("stock-ledger", "Stock ledger",
                             ["Date", "Site", "Code", "Material", "Unit", "Type", "Qty", "Rate", "Source", "Indent", "Ref",
                              "Party", "Note", "By"],
                             ([e.date, e.site.name, e.material.code, e.material.name, e.material.unit, e.get_kind_display(),
                               e.qty, e.rate, e.get_source_display(), e.indent.number if e.indent else "", e.ref, e.party,
                               e.note, e.by.name] for e in qs))
