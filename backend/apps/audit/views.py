from rest_framework import mixins, permissions, serializers, viewsets

from apps.accounts.permissions import IsAdmin

from .models import AuditLog


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.name", read_only=True, default="")

    class Meta:
        model = AuditLog
        fields = ["id", "at", "actor", "actor_name", "action", "target_type", "target_id", "summary", "changes", "ip"]


class AuditViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Administrator only. Filter with ?action=login.failed&actor=3&target_type=indent&target_id=12"""
    queryset = AuditLog.objects.select_related("actor")
    serializer_class = AuditSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    filterset_fields = ["action", "actor", "target_type", "target_id"]
    search_fields = ["summary", "action"]
