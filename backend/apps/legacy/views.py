from django.db.models import Count
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action, api_view, parser_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin
from apps.audit.log import record
from apps.materials import importer

from . import v1
from .models import V1Record

MAX_FILES = 6


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated, IsAdmin])
@parser_classes([MultiPartParser, FormParser])
def import_v1(request):
    """Upload the v1 Google Sheets (.xlsx) and/or the v1 export (.json). commit=false previews, commit=true applies."""
    files = request.FILES.getlist("files")
    if not files:
        raise ValidationError({"detail": "Choose the spreadsheet files to upload."})
    if len(files) > MAX_FILES:
        raise ValidationError({"detail": f"Up to {MAX_FILES} files at a time."})
    commit = str(request.data.get("commit", "false")).lower() in ("1", "true", "yes")
    try:
        res = v1.run([(f.name, f.read()) for f in files], request.user, commit)
    except importer.ImportError_ as e:
        raise ValidationError({"detail": str(e)})
    if commit:
        record("import.v1", actor=request.user, summary="Imported SiteOS v1 data from " + ", ".join(f.name for f in files),
               changes={k: {kk: vv for kk, vv in v.items() if kk != "errors"} for k, v in res["applied"].items()},
               request=request)
    return Response(res)


class V1RecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = V1Record
        fields = ["id", "tab", "row_no", "data", "source_file", "imported_at"]


class V1RecordViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Browse the kept v1 rows. ?tab=Labour"""
    queryset = V1Record.objects.all()
    serializer_class = V1RecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filterset_fields = ["tab"]

    @action(detail=False, methods=["get"])
    def tabs(self, request):
        return Response([{"tab": r["tab"], "rows": r["n"]} for r in
                         V1Record.objects.values("tab").annotate(n=Count("id")).order_by("tab")])


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated, IsAdmin])
def demo_data(request):
    """Create (password given) or remove (remove=true) the demo logins and demo indents."""
    import io

    from django.core.management import call_command
    from django.core.management.base import CommandError
    out = io.StringIO()
    try:
        if request.data.get("remove"):
            call_command("seed_demo", remove=True, stdout=out)
            record("demo.remove", actor=request.user, summary="Demo data switched off", request=request)
        else:
            call_command("seed_demo", password=str(request.data.get("password") or ""), stdout=out)
            record("demo.create", actor=request.user, summary="Demo logins and indents created", request=request)
    except CommandError as e:
        raise ValidationError({"detail": str(e)})
    return Response({"output": out.getvalue()})
