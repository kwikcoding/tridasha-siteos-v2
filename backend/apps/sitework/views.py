from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.scoped import ScopedViewSet, check_site
from apps.sites.models import Project, Site

from .models import Attendance, DailyReport, Task, Worker
from .serializers import (AttendanceSerializer, DailyReportSerializer, MarkSerializer, TaskSerializer,
                          WorkerSerializer, check_ot)


def notify(user, title, body, link, key):
    from apps.alerts.tasks import notify as _n
    transaction.on_commit(lambda: _n(user, "task", title, body, dedupe_key=key, link=link))


# ---------------------------------------------------------------- tasks
class TaskViewSet(ScopedViewSet):
    module = "tasks"
    queryset = Task.objects.select_related("site", "project", "assignee", "depends_on", "created_by")
    serializer_class = TaskSerializer
    date_field = "due_date"
    audit_label = "task"
    search_fields = ["title", "description"]
    extra_codes = {"progress": "tasks.view"}
    export_columns = [("Site", "site.name"), ("Project", "project.name"), ("Task", "title"),
                      ("Assigned to", "assignee.name"), ("Priority", "get_priority_display"),
                      ("Status", "get_status_display"), ("Start", "start_date"), ("Due", "due_date"),
                      ("Progress %", "progress"), ("Days overdue", "days_overdue"), ("Completed", "completed_at")]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("mine") == "1":
            qs = qs.filter(assignee=self.request.user)
        if p.get("assignee"):
            qs = qs.filter(assignee_id=p["assignee"])
        if p.get("overdue") == "1":
            qs = qs.filter(due_date__lt=timezone.localdate()).exclude(status__in=Task.CLOSED)
        if p.get("open") == "1":
            qs = qs.exclude(status__in=Task.CLOSED)
        return qs

    def _announce(self, task, before=None):
        if task.assignee_id and task.assignee_id != self.request.user.pk and task.assignee_id != before:
            notify(task.assignee, f"Task assigned to you — {task.title}",
                   f"{task.site.name}{' · due ' + task.due_date.strftime('%d %b') if task.due_date else ''}",
                   f"/tasks?id={task.pk}", f"task:{task.pk}:{task.assignee_id}")

    def perform_create(self, ser):
        super().perform_create(ser)
        self._announce(ser.instance)

    def perform_update(self, ser):
        before = ser.instance.assignee_id
        super().perform_update(ser)
        self._announce(ser.instance, before)

    @action(detail=True, methods=["post"])
    def progress(self, request, pk=None):
        """The assignee (or anyone who can edit tasks) updates status / progress with a note."""
        t = self.get_object()
        if t.assignee_id != request.user.pk and not request.user.has_code("tasks.edit"):
            raise PermissionDenied("Only the person the task is assigned to can update it.")
        data = {k: request.data[k] for k in ("status", "progress") if k in request.data}
        ser = TaskSerializer(t, data=data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        before = {"status": t.status, "progress": t.progress}
        ser.save()
        self.log(t, "progress", f"Task {t.title}: {t.get_status_display()} {t.progress}%",
                 before=before, note=str(request.data.get("note") or "")[:500])
        return Response(TaskSerializer(t, context=self.get_serializer_context()).data)


# ---------------------------------------------------------------- daily progress
class DailyReportViewSet(ScopedViewSet):
    module = "dpr"
    queryset = DailyReport.objects.select_related("site", "project", "created_by", "reviewed_by")
    serializer_class = DailyReportSerializer
    audit_label = "daily report"
    search_fields = ["summary", "issues"]
    extra_codes = {"submit": "dpr.create", "approve": "dpr.approve", "send_back": "dpr.approve",
                   "summary": "dpr.view", "destroy": "dpr.edit"}
    export_columns = [("Date", "date"), ("Site", "site.name"), ("Project", "project.name"),
                      ("Weather", "get_weather_display"), ("Manpower", "manpower_total"), ("Summary", "summary"),
                      ("Issues", "issues"), ("Status", "get_status_display"), ("By", "created_by.name"),
                      ("Approved by", "reviewed_by.name")]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def _own_or_editor(self, r):
        u = self.request.user
        if r.created_by_id != u.pk and not u.has_code("dpr.edit"):
            raise PermissionDenied("Only the person who wrote this report can change it.")

    def perform_update(self, ser):
        self._own_or_editor(ser.instance)
        super().perform_update(ser)

    def perform_destroy(self, r):
        self._own_or_editor(r)
        if r.status != "draft":
            raise ValidationError({"detail": "Only a draft can be deleted."})
        super().perform_destroy(r)

    def check_attach(self, r):
        if not r.editable:
            raise ValidationError({"detail": "This report is submitted — add photos before submitting."})

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        r = self.get_object()
        self._own_or_editor(r)
        if not r.editable:
            raise ValidationError({"detail": "This report is already submitted."})
        if not (r.summary.strip() or r.work_items):
            raise ValidationError({"detail": "Write what was done today (summary or work items) before submitting."})
        r.status, r.submitted_at = "submitted", timezone.now()
        r.save(update_fields=["status", "submitted_at"])
        self.log(r, "submit", f"Submitted {r}")
        for u in _approvers(r.site, "dpr.approve", exclude=request.user):
            notify(u, f"Daily report to approve — {r.site.name} {r.date:%d %b}", r.summary[:120], f"/dpr?id={r.pk}",
                   f"dpr:{r.pk}:{int(r.submitted_at.timestamp())}")
        return Response(self.get_serializer(r).data)

    def _review(self, request, new_status):
        r = self.get_object()
        if r.status != "submitted":
            raise ValidationError({"detail": "Only a submitted report can be reviewed."})
        if r.created_by_id == request.user.pk and not request.user.is_admin:
            raise PermissionDenied("You can’t approve your own report.")
        note = str(request.data.get("note") or "").strip()
        if new_status == "returned" and not note:
            raise ValidationError({"note": "Say what needs to change."})
        r.status, r.reviewed_by, r.reviewed_at, r.review_note = new_status, request.user, timezone.now(), note
        r.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
        self.log(r, "approve" if new_status == "approved" else "return", f"{r} {r.get_status_display().lower()}",
                 note=note)
        if new_status == "returned":
            notify(r.created_by, f"Daily report returned — {r.date:%d %b}", note, f"/dpr?id={r.pk}", f"dprret:{r.pk}:{int(r.reviewed_at.timestamp())}")
        return Response(self.get_serializer(r).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._review(request, "approved")

    @action(detail=True, methods=["post"], url_path="send-back")
    def send_back(self, request, pk=None):
        return self._review(request, "returned")

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Project-wise progress for the filtered period: reports, approved, man-days, quantities per activity."""
        qs = self.filter_queryset(self.get_queryset())
        out = {}
        for r in qs:
            key = (r.site.name, r.project.name if r.project else "—")
            row = out.setdefault(key, {"site": key[0], "project": key[1], "reports": 0, "approved": 0, "manpower": 0,
                                       "activities": {}})
            row["reports"] += 1
            row["approved"] += r.status == "approved"
            row["manpower"] += r.manpower_total
            for w in r.work_items or []:
                k = f"{w.get('activity', '')} ({w.get('unit', '')})".strip()
                row["activities"][k] = round(row["activities"].get(k, 0) + float(w.get("qty") or 0), 3)
        return Response(sorted(out.values(), key=lambda x: (x["site"], x["project"])))


def _approvers(site, code, exclude=None):
    from apps.accounts.models import User
    for u in User.objects.filter(is_active=True).prefetch_related("sites"):
        if u == exclude or not u.has_code(code):
            continue
        if u.all_sites or site.pk in u.site_ids():
            yield u


# ---------------------------------------------------------------- labour
class WorkerViewSet(ScopedViewSet):
    module = "labour"
    queryset = Worker.objects.select_related("site", "created_by")
    serializer_class = WorkerSerializer
    date_field = None
    audit_label = "worker"
    http_method_names = ["get", "post", "patch", "head", "options"]     # deactivate, never delete
    search_fields = ["name", "worker_code", "trade", "contractor"]
    export_columns = [("Site", "site.name"), ("Code", "worker_code"), ("Name", "name"), ("Trade", "trade"),
                      ("Contractor", "contractor"), ("Mobile", "mobile"), ("Daily wage (₹)", "daily_wage"),
                      ("OT rate / hr (₹)", "ot_rate"), ("Active", "active")]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(active=True)
        return qs


class AttendanceViewSet(ScopedViewSet):
    module = "labour"
    queryset = Attendance.objects.select_related("worker", "site", "project")
    serializer_class = AttendanceSerializer
    audit_label = "attendance"
    http_method_names = ["get", "patch", "delete", "head", "options", "post"]
    extra_codes = {"mark": "labour.create", "approve_day": "labour.approve", "summary": "labour.view",
                   "destroy": "labour.edit", "create": "labour.create"}
    export_columns = [("Date", "date"), ("Site", "site.name"), ("Project", "project.name"), ("Worker", "worker.name"),
                      ("Trade", "worker.trade"), ("Contractor", "worker.contractor"), ("Status", "get_status_display"),
                      ("OT hours", "ot_hours"), ("Wage (₹)", "wage"), ("Approved", "approved")]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("worker"):
            qs = qs.filter(worker_id=self.request.query_params["worker"])
        if self.request.query_params.get("contractor"):
            qs = qs.filter(worker__contractor=self.request.query_params["contractor"])
        return qs

    def create(self, request, *args, **kwargs):
        raise ValidationError({"detail": "Use attendance/mark/ to mark a day."})

    def perform_update(self, ser):
        obj = ser.save()
        obj.compute_wage()
        obj.save(update_fields=["wage"])
        self.log(obj, "update", f"Attendance changed: {obj.worker.name} {obj.date}", status=obj.status, ot=obj.ot_hours)

    def perform_destroy(self, obj):
        if obj.approved:
            raise ValidationError({"detail": "This day is approved — attendance can’t be removed."})
        super().perform_destroy(obj)

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def mark(self, request):
        """Mark (or correct) a day's attendance for several workers at once. Approved days are locked."""
        ser = MarkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        site = Site.objects.filter(pk=v["site"]).first()
        check_site(request.user, site)
        project = None
        if v.get("project"):
            project = Project.objects.filter(pk=v["project"], site=site).first()
            if project is None:
                raise ValidationError({"project": "This project belongs to another site."})
        workers = {w.pk: w for w in Worker.objects.select_for_update().filter(site=site, pk__in=[
            e.get("worker") for e in v["entries"]])}
        seen, saved = set(), []
        for n, e in enumerate(v["entries"], start=1):
            wid = e.get("worker")
            w = workers.get(wid)
            if w is None:
                raise ValidationError({"entries": f"Row {n}: worker isn’t on this site’s roll."})
            if wid in seen:
                raise ValidationError({"entries": f"Row {n}: {w.name} is listed twice."})
            seen.add(wid)
            status = e.get("status")
            if status not in Attendance.DAY_FACTOR:
                raise ValidationError({"entries": f"Row {n}: choose present, half, absent or leave."})
            if not w.active and status in ("present", "half"):
                raise ValidationError({"entries": f"Row {n}: {w.name} is marked inactive."})
            ot = check_ot(status, e.get("ot_hours"))
            a = Attendance.objects.filter(worker=w, date=v["date"]).first()
            if a and a.approved:
                raise ValidationError({"entries": f"{v['date']:%d %b} is approved — attendance is locked."})
            if a is None:
                a = Attendance(worker=w, date=v["date"], created_by=request.user)
            a.site, a.project, a.status, a.ot_hours, a.note = site, project, status, ot, str(e.get("note") or "")[:200]
            a.compute_wage()
            a.save()
            saved.append(a)
        from apps.audit.log import record
        record("labour.mark", actor=request.user, target_type="attendance", target_id=f"{site.pk}:{v['date']}",
               summary=f"Attendance marked for {len(saved)} at {site.name} on {v['date']:%d %b %Y}", request=request)
        return Response(AttendanceSerializer(saved, many=True).data, status=http.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="approve-day")
    @transaction.atomic
    def approve_day(self, request):
        site = Site.objects.filter(pk=request.data.get("site")).first()
        check_site(request.user, site, writing=False)
        date = request.data.get("date")
        qs = Attendance.objects.select_for_update().filter(site=site, date=date, approved=False)
        n = qs.update(approved=True, approved_by=request.user)
        if not n:
            raise ValidationError({"detail": "Nothing to approve for that day."})
        from apps.audit.log import record
        record("labour.approve", actor=request.user, target_type="attendance", target_id=f"{site.pk}:{date}",
               summary=f"Attendance approved: {n} marks at {site.name} on {date}", request=request)
        return Response({"approved": n})

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Totals for the filtered period: by day and by worker (days worked, OT, wages)."""
        qs = self.filter_queryset(self.get_queryset())
        by_day = list(qs.values("date").annotate(
            present=Count("id", filter=Q(status="present")), half=Count("id", filter=Q(status="half")),
            absent=Count("id", filter=Q(status="absent")), leave=Count("id", filter=Q(status="leave")),
            ot_hours=Sum("ot_hours"), wages=Sum("wage")).order_by("-date"))
        by_worker = list(qs.values("worker", "worker__name", "worker__trade", "worker__contractor").annotate(
            present=Count("id", filter=Q(status="present")), half=Count("id", filter=Q(status="half")),
            absent=Count("id", filter=Q(status="absent")), ot_hours=Sum("ot_hours"), wages=Sum("wage"))
            .order_by("worker__name"))
        for r in by_worker:
            r["days"] = r["present"] + Decimal("0.5") * r["half"]
        tot = qs.aggregate(wages=Sum("wage"), ot_hours=Sum("ot_hours"))
        man_days = sum(r["days"] for r in by_worker)
        return Response({"by_day": by_day, "by_worker": by_worker, "total_wages": tot["wages"] or 0,
                         "total_ot_hours": tot["ot_hours"] or 0, "man_days": man_days})
