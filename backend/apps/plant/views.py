from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.scoped import ScopedViewSet, check_site, user_site_ids
from apps.sites.models import Project, Site

from .models import Allocation, Equipment, MaintenanceLog
from .serializers import EquipmentSerializer, MaintenanceSerializer


def _date(v, default=None):
    d = parse_date(str(v)) if v else None
    return d or default


class EquipmentViewSet(ScopedViewSet):
    """The register is shared by all sites. People not on all sites see equipment at their sites plus what is free."""
    module = "equipment"
    queryset = Equipment.objects.select_related("site", "project").prefetch_related(
        "allocations__site", "allocations__project", "allocations__by", "maintenance__by")
    serializer_class = EquipmentSerializer
    date_field = None
    audit_label = "equipment"
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ["code", "name", "category", "reg_no"]
    extra_codes = {"allocate": "equipment.edit", "release": "equipment.edit", "log_maintenance": "equipment.edit",
                   "back_in_service": "equipment.edit", "utilisation": "equipment.view"}
    export_columns = [("Code", "code"), ("Name", "name"), ("Category", "category"), ("Make / model", "make_model"),
                      ("Reg no", "reg_no"), ("Ownership", "get_ownership_display"), ("Hire rate / day (₹)", "hire_rate"),
                      ("Status", "get_status_display"), ("Site", "site.name"), ("Project", "project.name"),
                      ("Next service", "next_service_due"), ("Service overdue", "service_overdue")]

    def scope(self, qs):
        ids = user_site_ids(self.request.user)
        return qs if ids is None else qs.filter(Q(site__in=ids) | Q(site__isnull=True))

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("service_due") == "1":
            qs = qs.filter(next_service_due__lte=timezone.localdate()).exclude(status="disposed")
        return qs

    def _locked(self):
        return Equipment.objects.select_for_update().get(pk=self.get_object().pk)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def allocate(self, request, pk=None):
        e = self._locked()
        if e.status != "available":
            raise ValidationError({"detail": f"{e.code} is {e.get_status_display().lower()} — release it first."})
        site = Site.objects.filter(pk=request.data.get("site")).first()
        check_site(request.user, site)
        project = None
        if request.data.get("project"):
            project = Project.objects.filter(pk=request.data["project"], site=site).first()
            if project is None:
                raise ValidationError({"project": "This project belongs to another site."})
        start = _date(request.data.get("from_date"), timezone.localdate())
        last = e.allocations.exclude(to_date__isnull=True).order_by("-to_date").first()
        if last and start <= last.to_date:
            raise ValidationError({"from_date": f"It was at {last.site.name} until {last.to_date:%d %b %Y}."})
        Allocation.objects.create(equipment=e, site=site, project=project, from_date=start,
                                  note=str(request.data.get("note") or "")[:200], by=request.user)
        e.status, e.site, e.project = "in_use", site, project
        e.save(update_fields=["status", "site", "project"])
        self.log(e, "allocate", f"{e.code} sent to {site.name}", site=site.pk, project=project.pk if project else None)
        return Response(self.get_serializer(Equipment.objects.get(pk=e.pk)).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def release(self, request, pk=None):
        e = self._locked()
        a = e.allocations.filter(to_date__isnull=True).first()
        if a is None:
            raise ValidationError({"detail": f"{e.code} isn’t allocated anywhere."})
        check_site(request.user, a.site, writing=False)
        end = _date(request.data.get("to_date"), timezone.localdate())
        if end < a.from_date:
            raise ValidationError({"to_date": "Release date is before it arrived."})
        a.to_date = end
        a.save(update_fields=["to_date"])
        if e.status == "in_use":
            e.status = "available"
        e.site, e.project = None, None
        e.save(update_fields=["status", "site", "project"])
        self.log(e, "release", f"{e.code} released from {a.site.name}")
        return Response(self.get_serializer(Equipment.objects.get(pk=e.pk)).data)

    @action(detail=True, methods=["post"], url_path="maintenance")
    @transaction.atomic
    def log_maintenance(self, request, pk=None):
        e = self._locked()
        ser = MaintenanceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        m = ser.save(equipment=e, by=request.user)
        if m.kind == "breakdown":
            e.status = "breakdown"
        elif m.kind in ("repair", "service") and request.data.get("out_of_service"):
            e.status = "maintenance"
        if m.kind == "service" and e.service_every_days:
            e.next_service_due = m.date + timedelta(days=e.service_every_days)
        e.save(update_fields=["status", "next_service_due"])
        self.log(e, "maintenance", f"{m.get_kind_display()} on {e.code}", cost=m.cost, downtime=m.downtime_hours)
        return Response(self.get_serializer(Equipment.objects.get(pk=e.pk)).data)

    @action(detail=True, methods=["post"], url_path="back-in-service")
    @transaction.atomic
    def back_in_service(self, request, pk=None):
        e = self._locked()
        if e.status not in ("maintenance", "breakdown"):
            raise ValidationError({"detail": "It isn’t out of service."})
        e.status = "in_use" if e.allocations.filter(to_date__isnull=True).exists() else "available"
        e.save(update_fields=["status"])
        self.log(e, "back_in_service", f"{e.code} back in service")
        return Response(self.get_serializer(e).data)

    @action(detail=False, methods=["get"])
    def utilisation(self, request):
        """Days allocated, downtime and hire cost per item for a period (default: this month)."""
        today = timezone.localdate()
        start = _date(request.query_params.get("from"), today.replace(day=1))
        end = _date(request.query_params.get("to"), today)
        if end < start:
            raise ValidationError({"to": "End is before start."})
        span = (end - start).days + 1
        site = request.query_params.get("site")
        rows = []
        for e in self.filter_queryset(self.get_queryset()):
            allocs = [a for a in e.allocations.all() if a.from_date <= end and (a.to_date is None or a.to_date >= start)
                      and (not site or str(a.site_id) == site)]
            days = sum(a.days_in(start, end) for a in allocs)
            logs = [m for m in e.maintenance.all() if start <= m.date <= end]
            down = sum(float(m.downtime_hours) for m in logs)
            rows.append({"id": e.id, "code": e.code, "name": e.name, "status": e.status, "days_allocated": days,
                         "utilisation_pct": round(100 * days / span, 1), "downtime_hours": down,
                         "maintenance_cost": float(sum(m.cost for m in logs)),
                         "hire_cost": float(e.hire_rate or 0) * days if e.ownership == "hired" else 0})
        return Response({"from": start, "to": end, "days": span, "rows": rows})
