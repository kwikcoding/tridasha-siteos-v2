from rest_framework import serializers

from .models import Project, Site


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = ["id", "code", "name", "address", "active", "created_at"]


class ProjectSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    head_name = serializers.CharField(source="head.name", read_only=True, default="")

    class Meta:
        model = Project
        fields = ["id", "site", "site_name", "code", "name", "status", "start_date", "end_date", "budget", "head",
                  "head_name", "description", "created_at"]

    def validate_code(self, v):
        return v.strip().upper()

    def validate(self, attrs):
        from apps.core.scoped import check_site
        site = attrs.get("site", getattr(self.instance, "site", None))
        if self.instance is not None and "site" in attrs and attrs["site"] != self.instance.site:
            raise serializers.ValidationError({"site": "A project can’t move to another site."})
        if self.instance is None:
            check_site(self.context["request"].user, site)
        s, e = attrs.get("start_date", getattr(self.instance, "start_date", None)), attrs.get(
            "end_date", getattr(self.instance, "end_date", None))
        if s and e and e < s:
            raise serializers.ValidationError({"end_date": "End date is before the start date."})
        if attrs.get("budget") is not None and attrs["budget"] < 0:
            raise serializers.ValidationError({"budget": "Budget can’t be negative."})
        code = attrs.get("code", getattr(self.instance, "code", ""))
        dup = Project.objects.filter(site=site, code=code)
        if self.instance is not None:
            dup = dup.exclude(pk=self.instance.pk)
        if site is not None and dup.exists():
            raise serializers.ValidationError({"code": f"{code} is already used at this site."})
        return attrs
