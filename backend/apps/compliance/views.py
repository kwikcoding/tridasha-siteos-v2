from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.models import ALLOWED_EXT, MAX_BYTES
from apps.core.scoped import ScopedViewSet, attachment_count

from .models import Document, DocumentRevision, Observation
from .serializers import DocumentSerializer, ObservationSerializer, RevisionSerializer

PREFIX = {"inspection": "QI", "safety": "SO", "incident": "INC", "ncr": "NCR", "near_miss": "NM"}


class ObservationViewSet(ScopedViewSet):
    module = "quality"
    queryset = Observation.objects.select_related("site", "project", "assigned_to", "closed_by", "created_by")
    serializer_class = ObservationSerializer
    audit_label = "item"
    http_method_names = ["get", "post", "patch", "head", "options"]       # closed, never deleted
    search_fields = ["ref_no", "title", "description", "location"]
    extra_codes = {"start": "quality.edit", "close": "quality.approve", "reopen": "quality.approve",
                   "summary": "quality.view"}
    export_columns = [("Ref", "ref_no"), ("Date", "date"), ("Site", "site.name"), ("Project", "project.name"),
                      ("Type", "get_kind_display"), ("Title", "title"), ("Location", "location"),
                      ("Severity", "get_severity_display"), ("Assigned to", "assigned_to.name"), ("Due", "due_date"),
                      ("Corrective action", "corrective_action"), ("Status", "get_status_display"),
                      ("Closed by", "closed_by.name"), ("Closed", "closed_at"), ("Closure note", "closure_note")]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        for k in ("kind", "status", "severity"):
            if p.get(k):
                qs = qs.filter(**{f"{k}__in": p[k].split(",")})
        if p.get("overdue") == "1":
            qs = qs.filter(due_date__lt=timezone.localdate()).exclude(status="closed")
        return qs

    @transaction.atomic
    def perform_create(self, ser):
        kind = ser.validated_data["kind"]
        prefix = f"{PREFIX[kind]}-{timezone.localdate():%y%m}-"
        n = Observation.objects.filter(ref_no__startswith=prefix).count() + 1
        while Observation.objects.filter(ref_no=f"{prefix}{n:03d}").exists():
            n += 1
        ser.validated_data["ref_no"] = f"{prefix}{n:03d}"
        super().perform_create(ser)
        o = ser.instance
        if o.assigned_to_id and o.assigned_to_id != self.request.user.pk:
            from apps.sitework.views import notify
            notify(o.assigned_to, f"{o.get_kind_display()} assigned to you — {o.ref_no}", o.title,
                   f"/quality?id={o.pk}", f"obs:{o.pk}")

    def check_attach(self, o):
        if o.status == "closed":
            raise ValidationError({"detail": "This item is closed."})

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        o = self.get_object()
        if o.status != "open":
            raise ValidationError({"detail": "Only an open item can be started."})
        o.status = "in_progress"
        o.save(update_fields=["status"])
        self.log(o, "start", f"{o.ref_no} in progress")
        return Response(self.get_serializer(o).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        o = self.get_object()
        if o.status == "closed":
            raise ValidationError({"detail": "Already closed."})
        note = str(request.data.get("note") or "").strip()
        if not note:
            raise ValidationError({"note": "Write how it was resolved."})
        if not (o.corrective_action or "").strip():
            raise ValidationError({"detail": "Record the corrective action before closing."})
        if o.needs_evidence and not attachment_count(o, "evidence"):
            raise ValidationError({"detail": f"{o.get_kind_display()} ({o.get_severity_display().lower()}) needs a "
                                             "closure photo or document — attach it as evidence first."})
        o.status, o.closure_note, o.closed_by, o.closed_at = "closed", note, request.user, timezone.now()
        o.save(update_fields=["status", "closure_note", "closed_by", "closed_at"])
        self.log(o, "close", f"Closed {o.ref_no}", note=note)
        return Response(self.get_serializer(o).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        o = self.get_object()
        if o.status != "closed":
            raise ValidationError({"detail": "Only a closed item can be reopened."})
        note = str(request.data.get("note") or "").strip()
        if not note:
            raise ValidationError({"note": "Say why it’s being reopened."})
        o.status, o.closed_at, o.closed_by = "in_progress", None, None
        o.save(update_fields=["status", "closed_at", "closed_by"])
        self.log(o, "reopen", f"Reopened {o.ref_no}", note=note)
        return Response(self.get_serializer(o).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.filter_queryset(self.get_queryset())
        return Response({
            "by_kind": list(qs.values("kind").annotate(total=Count("id"), open=Count("id", filter=~Q(status="closed")))
                            .order_by("kind")),
            "open_by_severity": list(qs.exclude(status="closed").values("severity").annotate(n=Count("id"))
                                     .order_by("severity")),
            "overdue": qs.filter(due_date__lt=timezone.localdate()).exclude(status="closed").count(),
        })


class DocumentViewSet(ScopedViewSet):
    module = "docs"
    queryset = Document.objects.select_related("site", "project", "created_by").prefetch_related("revisions__uploaded_by")
    serializer_class = DocumentSerializer
    date_field = None
    audit_label = "document"
    search_fields = ["number", "title", "discipline"]
    extra_codes = {"upload": "docs.edit", "download": "docs.view", "archive": "docs.delete", "destroy": "docs.delete"}
    export_columns = [("Site", "site.name"), ("Project", "project.name"), ("Category", "get_category_display"),
                      ("Number", "number"), ("Title", "title"), ("Discipline", "discipline"),
                      ("Current revision", lambda d: next(iter(d.revisions.all()), None) and next(iter(d.revisions.all())).rev),
                      ("Revisions", lambda d: len(d.revisions.all())), ("Archived", "archived")]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("category"):
            qs = qs.filter(category=p["category"])
        if p.get("archived") != "1":
            qs = qs.filter(archived=False)
        return qs

    def perform_destroy(self, d):
        """Documents with files are archived, not deleted; only an empty record can be removed."""
        if d.revisions.exists():
            raise ValidationError({"detail": "This document has files — archive it instead. Files are never deleted."})
        super().perform_destroy(d)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        d = self.get_object()
        d.archived = not d.archived
        d.save(update_fields=["archived"])
        self.log(d, "archive", f"{'Archived' if d.archived else 'Restored'} {d}")
        return Response(self.get_serializer(d).data)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    @transaction.atomic
    def upload(self, request, pk=None):
        """Add a new revision. An existing revision's file is never replaced."""
        d = Document.objects.select_for_update().get(pk=self.get_object().pk)
        if d.archived:
            raise ValidationError({"detail": "This document is archived."})
        f = request.FILES.get("file")
        if not f:
            raise ValidationError({"file": "Choose a file."})
        ext = ("." + f.name.rsplit(".", 1)[-1].lower()) if "." in f.name else ""
        if ext not in ALLOWED_EXT:
            raise ValidationError({"file": "This file type isn’t allowed."})
        if f.size > MAX_BYTES:
            raise ValidationError({"file": "File is larger than 20 MB."})
        rev = str(request.data.get("rev") or "").strip().upper() or f"R{d.revisions.count()}"
        if d.revisions.filter(rev=rev).exists():
            raise ValidationError({"rev": f"Revision {rev} already exists — files are never replaced. Use the next revision."})
        status = request.data.get("status") or "For construction"
        if status not in dict(DocumentRevision._meta.get_field("status").choices):
            raise ValidationError({"status": "Unknown status."})
        if status == "For construction":
            d.revisions.filter(status="For construction").update(status="Superseded")
        r = DocumentRevision.objects.create(document=d, rev=rev, file=f, file_name=f.name[:200], size=f.size,
                                            note=str(request.data.get("note") or "")[:300], status=status,
                                            uploaded_by=request.user)
        self.log(d, "upload", f"Revision {rev} of {d.number} uploaded", rev=rev, file=r.file_name)
        return Response(RevisionSerializer(r).data, status=http.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path=r"revisions/(?P<rev_id>\d+)/download")
    def download(self, request, pk=None, rev_id=None):
        d = self.get_object()
        r = d.revisions.filter(pk=rev_id).first()
        if not r:
            raise Http404
        self.log(d, "download", f"Downloaded {d.number} {r.rev}")
        return FileResponse(r.file.open("rb"), as_attachment=True, filename=r.file_name)
