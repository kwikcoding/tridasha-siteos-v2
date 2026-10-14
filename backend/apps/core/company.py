"""Settings → Company profile. Everyone signed in can read it (it heads reports and exports);
only the administrator (settings.manage) can change it. Every change is in the audit log."""
import re

from django.http import FileResponse, Http404
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.log import diff, record

from .models import CompanyProfile

GSTIN_RE = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
STATE_CODES = {"36": "Telangana", "37": "Andhra Pradesh", "29": "Karnataka", "27": "Maharashtra", "33": "Tamil Nadu"}


class CompanySerializer(serializers.ModelSerializer):
    has_logo = serializers.SerializerMethodField()
    updated_by_name = serializers.CharField(source="updated_by.name", read_only=True, default="")

    class Meta:
        model = CompanyProfile
        fields = ["name", "legal_name", "gstin", "pan", "cin", "address", "city", "state", "pincode", "phone", "email",
                  "website", "financial_year_start", "has_logo", "updated_by_name", "updated_at"]

    def get_has_logo(self, obj):
        return bool(obj.logo)

    def validate_name(self, v):
        if not v.strip():
            raise serializers.ValidationError("Enter the company name.")
        return v.strip()

    def validate_gstin(self, v):
        v = v.strip().upper()
        if v and not GSTIN_RE.match(v):
            raise serializers.ValidationError("GSTIN is 15 characters, e.g. 36ABCDE1234F1Z5.")
        return v

    def validate_pan(self, v):
        v = v.strip().upper()
        if v and not PAN_RE.match(v):
            raise serializers.ValidationError("PAN is 10 characters, e.g. ABCDE1234F.")
        return v

    def validate_pincode(self, v):
        v = v.strip()
        if v and not re.fullmatch(r"[1-9][0-9]{5}", v):
            raise serializers.ValidationError("PIN code is 6 digits.")
        return v

    def validate_phone(self, v):
        v = v.strip()
        if v and not re.fullmatch(r"[+0-9 ()-]{6,20}", v):
            raise serializers.ValidationError("Enter a phone number (digits, spaces, + and -).")
        return v

    def validate(self, attrs):
        gstin = attrs.get("gstin", getattr(self.instance, "gstin", ""))
        pan = attrs.get("pan", getattr(self.instance, "pan", ""))
        if gstin and pan and gstin[2:12] != pan:
            raise serializers.ValidationError({"gstin": "The GSTIN doesn't contain this PAN (characters 3–12 should match)."})
        return attrs


def _can_manage(user):
    return user.is_admin or user.has_code("settings.manage")


@api_view(["GET", "PATCH", "PUT"])
@permission_classes([permissions.IsAuthenticated])
def company(request):
    obj = CompanyProfile.load()
    if request.method == "GET":
        return Response(CompanySerializer(obj).data)
    if not _can_manage(request.user):
        raise PermissionDenied("Only the administrator can change the company profile.")
    ser = CompanySerializer(obj, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    changes = diff(obj, ser.validated_data)
    ser.save(updated_by=request.user)
    if changes:
        record("settings.company", actor=request.user, target=obj, summary="Company profile changed", changes=changes,
               request=request)
    return Response(CompanySerializer(obj).data)


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def company_logo(request):
    obj = CompanyProfile.load()
    if request.method == "GET":
        if not obj.logo:
            raise Http404
        return FileResponse(obj.logo.open("rb"))
    if not _can_manage(request.user):
        raise PermissionDenied("Only the administrator can change the logo.")
    f = request.FILES.get("file")
    if not f:
        raise ValidationError({"file": "Choose an image."})
    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise ValidationError({"file": "Use a PNG, JPG or WEBP image."})
    if f.size > 2 * 1024 * 1024:
        raise ValidationError({"file": "Logo must be under 2 MB."})
    obj.logo = f                      # the previous file stays on disk; only the pointer changes
    obj.updated_by = request.user
    obj.save()
    record("settings.company_logo", actor=request.user, target=obj, summary="Company logo changed", request=request)
    return Response(CompanySerializer(obj).data)
