from rest_framework import permissions, viewsets

from apps.accounts.permissions import IsAdmin

from .models import Site
from .serializers import SiteSerializer


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
