from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.core.scoped import SiteProjectSerializer

from .models import Attendance, DailyReport, Task, Worker


def _user_on_site(user, site):
    return user.is_active and (user.all_sites or site.pk in user.site_ids())


class TaskSerializer(SiteProjectSerializer):
    assignee_name = serializers.CharField(source="assignee.name", read_only=True, default="")
    depends_on_title = serializers.CharField(source="depends_on.title", read_only=True, default="")
    overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)

    class Meta:
        model = Task
        fields = ["id", "site", "site_name", "project", "project_name", "title", "description", "assignee",
                  "assignee_name", "priority", "status", "start_date", "due_date", "progress", "depends_on",
                  "depends_on_title", "overdue", "days_overdue", "completed_at", "created_by_name", "created_at",
                  "updated_at"]
        read_only_fields = ["completed_at", "created_at", "updated_at"]

    def validate_progress(self, v):
        if v > 100:
            raise serializers.ValidationError("Progress is a percentage (0–100).")
        return v

    def validate(self, attrs):
        attrs = super().validate(attrs)
        req = self.context["request"]
        site = attrs.get("site", getattr(self.instance, "site", None))
        a = attrs.get("assignee", serializers.empty)
        if a is not serializers.empty and a is not None:
            if a != req.user and not req.user.has_code("tasks.assign"):
                raise serializers.ValidationError({"assignee": "Your role can assign tasks only to yourself."})
            if not _user_on_site(a, site):
                raise serializers.ValidationError({"assignee": f"{a.name} isn’t assigned to this site."})
        s = attrs.get("start_date", getattr(self.instance, "start_date", None))
        d = attrs.get("due_date", getattr(self.instance, "due_date", None))
        if s and d and d < s:
            raise serializers.ValidationError({"due_date": "Due date is before the start date."})
        dep = attrs.get("depends_on", getattr(self.instance, "depends_on", None))
        if dep is not None:
            if dep.site_id != site.pk:
                raise serializers.ValidationError({"depends_on": "Depends on a task at another site."})
            node, seen = dep, set()
            while node is not None:
                if self.instance is not None and node.pk == self.instance.pk:
                    raise serializers.ValidationError({"depends_on": "That would make a loop of dependencies."})
                if node.pk in seen:
                    break
                seen.add(node.pk)
                node = node.depends_on
        status = attrs.get("status")
        if status == "done" and dep is not None and dep.status != "done":
            raise serializers.ValidationError({"status": f"“{dep.title}” has to be done first."})
        if status == "done":
            attrs["progress"] = 100
            if not (self.instance and self.instance.completed_at):
                attrs["completed_at"] = timezone.now()
        elif status and status != "done":
            attrs["completed_at"] = None
        return attrs


class DailyReportSerializer(SiteProjectSerializer):
    manpower_total = serializers.IntegerField(read_only=True)
    editable = serializers.BooleanField(read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.name", read_only=True, default="")
    labour_marked = serializers.SerializerMethodField()

    class Meta:
        model = DailyReport
        fields = ["id", "site", "site_name", "project", "project_name", "date", "weather", "summary", "work_items",
                  "manpower", "manpower_total", "materials_used", "issues", "tomorrow_plan", "status", "editable",
                  "created_by", "created_by_name", "created_at", "submitted_at", "reviewed_by_name", "reviewed_at",
                  "review_note", "labour_marked"]
        read_only_fields = ["status", "created_by", "submitted_at", "reviewed_at", "review_note"]
        validators = []      # one report per site/project/day is checked in validate() with a plain-language message

    def get_labour_marked(self, obj):
        """Attendance marked for the same site/day — a cross-check against the manpower in the report.
        Only on a single report (it would cost two queries per row in a list)."""
        view = self.context.get("view")
        if view is not None and getattr(view, "action", "") != "retrieve":
            return None
        qs = Attendance.objects.filter(site=obj.site, date=obj.date)
        if obj.project_id:
            qs = qs.filter(project=obj.project)
        return {"present": qs.filter(status="present").count(), "half": qs.filter(status="half").count()}

    @staticmethod
    def _rows(value, keys, numeric, label, limit=100):
        if not isinstance(value, list) or len(value) > limit:
            raise serializers.ValidationError(f"{label}: up to {limit} rows.")
        out = []
        for r in value:
            if not isinstance(r, dict):
                raise serializers.ValidationError(f"{label}: each row must be an object.")
            row = {k: r.get(k) for k in keys if r.get(k) not in (None, "")}
            if not row:
                continue
            for k in numeric:
                if k in row:
                    try:
                        n = float(row[k])
                    except (TypeError, ValueError):
                        raise serializers.ValidationError(f"{label}: {k} must be a number.")
                    if n < 0:
                        raise serializers.ValidationError(f"{label}: {k} can’t be negative.")
                    row[k] = n
            out.append(row)
        return out

    def validate_work_items(self, v):
        return self._rows(v, ["activity", "location", "qty", "unit", "planned_qty"], ["qty", "planned_qty"], "Work done")

    def validate_manpower(self, v):
        rows = self._rows(v, ["trade", "count"], ["count"], "Manpower", 50)
        for r in rows:
            r["count"] = int(r.get("count") or 0)
        return rows

    def validate_materials_used(self, v):
        return self._rows(v, ["item", "qty", "unit"], ["qty"], "Materials used")

    def validate_date(self, v):
        if v > timezone.localdate():
            raise serializers.ValidationError("A daily report can’t be for a future date.")
        return v

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and not self.instance.editable:
            raise serializers.ValidationError("This report is submitted — it can be changed only after it’s returned.")
        site = attrs.get("site", getattr(self.instance, "site", None))
        project = attrs.get("project", getattr(self.instance, "project", None))
        d = attrs.get("date", getattr(self.instance, "date", None))
        dup = DailyReport.objects.filter(site=site, project=project, date=d)
        if self.instance is not None:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            where = f"{project.name} " if project else ""
            raise serializers.ValidationError(f"There is already a daily report for {where}{site.name} on {d:%d %b %Y}.")
        return attrs


class WorkerSerializer(SiteProjectSerializer):
    class Meta:
        model = Worker
        fields = ["id", "site", "site_name", "name", "worker_code", "trade", "contractor", "mobile", "daily_wage",
                  "ot_rate", "active", "created_by_name", "created_at"]
        extra_kwargs = {"worker_code": {"required": False}}
        validators = []          # the code is optional; uniqueness per site is checked in validate()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for k in ("daily_wage", "ot_rate"):
            if attrs.get(k) is not None and attrs[k] < 0:
                raise serializers.ValidationError({k: "Can’t be negative."})
        code = (attrs.get("worker_code") or "").strip()
        if code:
            site = attrs.get("site", getattr(self.instance, "site", None))
            dup = Worker.objects.filter(site=site, worker_code=code)
            if self.instance is not None:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise serializers.ValidationError({"worker_code": f"{code} is already used at this site."})
        if self.instance is not None and "site" in attrs and attrs["site"] != self.instance.site \
                and self.instance.attendance.exists():
            raise serializers.ValidationError({"site": "This worker has attendance here — add them again at the new site."})
        return attrs


class AttendanceSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.name", read_only=True)
    trade = serializers.CharField(source="worker.trade", read_only=True)
    contractor = serializers.CharField(source="worker.contractor", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = Attendance
        fields = ["id", "worker", "worker_name", "trade", "contractor", "site", "site_name", "project", "date",
                  "status", "ot_hours", "wage", "note", "approved", "updated_at"]
        read_only_fields = ["worker", "site", "project", "date", "wage", "approved"]

    def validate(self, attrs):
        if self.instance is not None and self.instance.approved:
            raise serializers.ValidationError("This day is approved — attendance can’t be changed.")
        status = attrs.get("status", getattr(self.instance, "status", None))
        ot = attrs.get("ot_hours", getattr(self.instance, "ot_hours", Decimal("0")))
        check_ot(status, ot)
        return attrs


def check_ot(status, ot):
    ot = Decimal(str(ot or 0))
    if ot < 0 or ot > 12:
        raise serializers.ValidationError({"ot_hours": "Overtime must be between 0 and 12 hours."})
    if ot > 0 and status not in ("present", "half"):
        raise serializers.ValidationError({"ot_hours": "Overtime only for someone who was present."})
    return ot


class MarkSerializer(serializers.Serializer):
    site = serializers.IntegerField()
    project = serializers.IntegerField(required=False, allow_null=True)
    date = serializers.DateField()
    entries = serializers.ListField(child=serializers.DictField(), max_length=1000)

    def validate_date(self, v):
        if v > timezone.localdate():
            raise serializers.ValidationError("Attendance can’t be marked for a future date.")
        return v
