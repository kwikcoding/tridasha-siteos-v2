"""Base pieces for the site-work modules: one place for site/project isolation, permissions, audit and export."""
from datetime import date, datetime

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import module_permission
from apps.audit.log import diff, record

from .models import ALLOWED_EXT, MAX_BYTES, Attachment


def user_site_ids(user):
    return None if user.all_sites else set(user.site_ids())


def check_site(user, site, *, writing=True):
    """Refuse a site the person isn't assigned to, and (for new records) a closed site."""
    if site is None:
        raise ValidationError({"site": "Choose a site."})
    ids = user_site_ids(user)
    if ids is not None and site.pk not in ids:
        raise ValidationError({"site": "You aren’t assigned to this site."})
    if writing and not site.active:
        raise ValidationError({"site": "This site is closed."})


class SiteProjectSerializer(serializers.ModelSerializer):
    """Adds site/project names and checks that the project belongs to the site."""
    site_name = serializers.CharField(source="site.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    created_by_name = serializers.CharField(source="created_by.name", read_only=True, default="")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        site = attrs.get("site", getattr(self.instance, "site", None))
        project = attrs.get("project", getattr(self.instance, "project", None))
        if "site" in attrs or self.instance is None:
            check_site(self.context["request"].user, site, writing=self.instance is None)
        if project is not None and site is not None and project.site_id != site.pk:
            raise ValidationError({"project": "This project belongs to another site."})
        return attrs


def _cell(v):
    if isinstance(v, datetime):
        return timezone.localtime(v).replace(tzinfo=None) if timezone.is_aware(v) else v
    if hasattr(v, "pk"):
        return str(v)
    return v


class ScopedViewSet(viewsets.ModelViewSet):
    """Records that belong to a site (and optionally a project).

    Subclasses set: module, queryset, serializer_class, export_columns [(header, attr path)], date_field,
    and may set site_path (default "site") and extra_codes (action → permission code).
    """
    module = ""
    site_path = "site"
    date_field = "date"
    export_columns: list = []
    extra_codes: dict = {}
    audit_label = ""
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    search_fields: list = []
    ordering_fields = "__all__"

    def get_permissions(self):
        codes = {"export": f"{self.module}.export", "attachments": f"{self.module}.view",
                 "attach": f"{self.module}.edit", "attachment_file": f"{self.module}.view", **self.extra_codes}
        return [permissions.IsAuthenticated(), module_permission(self.module, **codes)()]

    def scope(self, qs):
        ids = user_site_ids(self.request.user)
        return qs if ids is None else qs.filter(**{f"{self.site_path}__in": ids})

    def get_queryset(self):
        qs = self.scope(super().get_queryset())
        p = self.request.query_params
        if p.get("site"):
            qs = qs.filter(**{f"{self.site_path}_id": p["site"]}) if self.site_path == "site" else qs.filter(
                **{f"{self.site_path}__id": p["site"]})
        if p.get("project") and self._has_field("project"):
            qs = qs.filter(project_id=p["project"])
        if self.date_field:
            if p.get("from") and parse_date(p["from"]):
                qs = qs.filter(**{f"{self.date_field}__gte": parse_date(p["from"])})
            if p.get("to") and parse_date(p["to"]):
                qs = qs.filter(**{f"{self.date_field}__lte": parse_date(p["to"])})
        return qs

    def _has_field(self, name):
        return any(f.name == name for f in self.queryset.model._meta.get_fields())

    # ---------------------------------------------------------------- audit
    def label(self, obj):
        return f"{self.audit_label or obj._meta.verbose_name} {obj}"

    def perform_create(self, ser):
        kw = {"created_by": self.request.user} if self._has_field("created_by") else {}
        obj = ser.save(**kw)
        record(f"{self.module}.create", actor=self.request.user, target=obj, summary=f"Added {self.label(obj)}",
               request=self.request)

    def perform_update(self, ser):
        changes = diff(ser.instance, ser.validated_data)
        obj = ser.save()
        if changes:
            record(f"{self.module}.update", actor=self.request.user, target=obj, summary=f"Changed {self.label(obj)}",
                   changes=changes, request=self.request)

    def perform_destroy(self, obj):
        record(f"{self.module}.delete", actor=self.request.user, target=obj, summary=f"Deleted {self.label(obj)}",
               request=self.request)
        obj.delete()

    def log(self, obj, verb, summary, **changes):
        record(f"{self.module}.{verb}", actor=self.request.user, target=obj, summary=summary, changes=changes,
               request=self.request)

    # ---------------------------------------------------------------- export
    @action(detail=False, methods=["get"])
    def export(self, request):
        from apps.materials.views import xlsx_response
        qs = self.filter_queryset(self.get_queryset())[:20000]

        def val(obj, path):
            if callable(path):
                return path(obj)
            for part in path.split("."):
                obj = getattr(obj, part, None) if obj is not None else None
                if callable(obj) and not hasattr(obj, "pk"):
                    obj = obj()
            return _cell(obj)
        return xlsx_response(self.module, self.module.title(), [h for h, _ in self.export_columns],
                             ([val(o, p) for _, p in self.export_columns] for o in qs))

    # ---------------------------------------------------------------- attachments
    @action(detail=True, methods=["get"])
    def attachments(self, request, pk=None):
        obj = self.get_object()
        ct = ContentType.objects.get_for_model(obj)
        base = _api_rel(request.path.split(f"{pk}/attachments/")[0] + f"{pk}/")
        return Response([a.as_dict(base) for a in Attachment.objects.filter(content_type=ct, object_id=obj.pk)
                         .select_related("uploaded_by")])

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def attach(self, request, pk=None):
        obj = self.get_object()
        self.check_attach(obj)
        f = request.FILES.get("file")
        if not f:
            raise ValidationError({"file": "Choose a file."})
        ext = ("." + f.name.rsplit(".", 1)[-1].lower()) if "." in f.name else ""
        if ext not in ALLOWED_EXT:
            raise ValidationError({"file": "This file type isn’t allowed."})
        if f.size > MAX_BYTES:
            raise ValidationError({"file": "File is larger than 20 MB."})
        a = Attachment.objects.create(record=obj, file=f, name=f.name[:200], size=f.size,
                                      purpose=str(request.data.get("purpose") or "")[:30], uploaded_by=request.user)
        self.log(obj, "attach", f"File {a.name} added to {self.label(obj)}", file=a.name, purpose=a.purpose)
        base = _api_rel(request.path.split(f"{pk}/attach/")[0] + f"{pk}/")
        return Response(a.as_dict(base), status=status.HTTP_201_CREATED)

    def check_attach(self, obj):
        """Override to refuse attachments on locked records."""

    @action(detail=True, methods=["get"], url_path=r"attachments/(?P<att_id>\d+)")
    def attachment_file(self, request, pk=None, att_id=None):
        obj = self.get_object()          # same permission + site check as the record
        ct = ContentType.objects.get_for_model(obj)
        a = Attachment.objects.filter(pk=att_id, content_type=ct, object_id=obj.pk).first()
        if not a:
            raise Http404
        return FileResponse(a.file.open("rb"), as_attachment=True, filename=a.name)


def _api_rel(path):
    """'/api/observations/5/' → '/observations/5/' (the frontend adds /api itself)."""
    return path[4:] if path.startswith("/api/") else path


def attachment_count(obj, purpose=None):
    qs = Attachment.objects.filter(content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk)
    return qs.filter(purpose=purpose).count() if purpose else qs.count()


def today():
    return timezone.localdate()


def as_date(v):
    if isinstance(v, date):
        return v
    return parse_date(str(v)) if v else None


def deny(msg):
    raise PermissionDenied(msg)
