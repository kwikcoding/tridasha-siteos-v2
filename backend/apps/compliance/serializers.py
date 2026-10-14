from rest_framework import serializers

from apps.core.scoped import SiteProjectSerializer, attachment_count

from .models import Document, DocumentRevision, Observation


class ObservationSerializer(SiteProjectSerializer):
    assigned_to_name = serializers.CharField(source="assigned_to.name", read_only=True, default="")
    closed_by_name = serializers.CharField(source="closed_by.name", read_only=True, default="")
    needs_evidence = serializers.BooleanField(read_only=True)
    overdue = serializers.BooleanField(read_only=True)
    evidence_files = serializers.SerializerMethodField()

    class Meta:
        model = Observation
        fields = ["id", "site", "site_name", "project", "project_name", "kind", "ref_no", "title", "description",
                  "location", "date", "severity", "assigned_to", "assigned_to_name", "due_date", "corrective_action",
                  "status", "needs_evidence", "evidence_files", "overdue", "closure_note", "closed_by_name",
                  "closed_at", "created_by_name", "created_at"]
        read_only_fields = ["ref_no", "status", "closure_note", "closed_at"]

    def get_evidence_files(self, obj):
        view = self.context.get("view")
        if view is not None and getattr(view, "action", "") == "list":
            return None              # shown in the detail window only (avoids a query per row)
        return attachment_count(obj, "evidence")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and self.instance.status == "closed":
            raise serializers.ValidationError("This item is closed — reopen it to make changes.")
        a = attrs.get("assigned_to")
        site = attrs.get("site", getattr(self.instance, "site", None))
        if a is not None and not (a.is_active and (a.all_sites or site.pk in a.site_ids())):
            raise serializers.ValidationError({"assigned_to": f"{a.name} isn’t assigned to this site."})
        return attrs


class RevisionSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.name", read_only=True)

    class Meta:
        model = DocumentRevision
        fields = ["id", "rev", "file_name", "size", "note", "status", "uploaded_by_name", "uploaded_at"]


class DocumentSerializer(SiteProjectSerializer):
    revisions = RevisionSerializer(many=True, read_only=True)
    current_rev = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "site", "site_name", "project", "project_name", "category", "number", "title", "discipline",
                  "archived", "current_rev", "revisions", "created_by_name", "created_at"]
        read_only_fields = ["archived"]
        validators = []      # number per site is checked in validate() (case-insensitive, plain-language message)

    def get_current_rev(self, obj):
        r = next(iter(obj.revisions.all()), None)
        return r.rev if r else ""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and "site" in attrs and attrs["site"] != self.instance.site:
            raise serializers.ValidationError({"site": "A document can’t move to another site."})
        site = attrs.get("site", getattr(self.instance, "site", None))
        num = (attrs.get("number", getattr(self.instance, "number", "")) or "").strip()
        if "number" in attrs:
            attrs["number"] = num
        dup = Document.objects.filter(site=site, number__iexact=num)
        if self.instance is not None:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            raise serializers.ValidationError({"number": f"{num} already exists at this site — upload a new revision to it."})
        return attrs
