from rest_framework import serializers

from .models import Site


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = ["id", "code", "name", "address", "active", "created_at"]
