from django.db.models import Count, Q
from rest_framework import permissions, viewsets

from apps.accounts.permissions import IsAdmin
from apps.core.scoped import ScopedViewSet

from .models import Project, Site
from .serializers import ProjectSerializer, SiteSerializer


class SiteViewSet(viewsets.ModelViewSet):
    serializer_class = SiteSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        u = self.request.user
        qs = Site.objects.all()
        return qs if u.all_sites else qs.filter(pk__in=u.site_ids())

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]   # everyone needs their own site list
        return [permissions.IsAuthenticated(), IsAdmin()]


class ProjectViewSet(ScopedViewSet):
    """Projects at the person's sites. Listing is open to everyone signed in (pickers need it);
    creating and editing need sites.create / sites.edit. Projects are closed, not deleted."""
    module = "sites"
    queryset = Project.objects.select_related("site", "head")
    serializer_class = ProjectSerializer
    pagination_class = None
    date_field = "start_date"
    audit_label = "project"
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ["code", "name"]
    export_columns = [("Site", "site.name"), ("Code", "code"), ("Project", "name"), ("Status", "get_status_display"),
                      ("Start", "start_date"), ("End", "end_date"), ("Budget (₹)", "budget"), ("Head", "head.name")]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("open") == "1":
            qs = qs.filter(status__in=["planned", "active", "on_hold"])
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs
