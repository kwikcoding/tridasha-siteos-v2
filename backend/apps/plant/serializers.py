from rest_framework import serializers

from .models import Allocation, Equipment, MaintenanceLog


class AllocationSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    by_name = serializers.CharField(source="by.name", read_only=True)

    class Meta:
        model = Allocation
        fields = ["id", "site", "site_name", "project", "project_name", "from_date", "to_date", "note", "by_name"]


class MaintenanceSerializer(serializers.ModelSerializer):
    by_name = serializers.CharField(source="by.name", read_only=True)

    class Meta:
        model = MaintenanceLog
        fields = ["id", "date", "kind", "description", "cost", "downtime_hours", "done_by", "by_name", "created_at"]

    def validate(self, attrs):
        for k in ("cost", "downtime_hours"):
            if attrs.get(k) is not None and attrs[k] < 0:
                raise serializers.ValidationError({k: "Can’t be negative."})
        return attrs


class EquipmentSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True, default="")
    project_name = serializers.CharField(source="project.name", read_only=True, default="")
    service_overdue = serializers.BooleanField(read_only=True)
    allocations = AllocationSerializer(many=True, read_only=True)
    maintenance = MaintenanceSerializer(many=True, read_only=True)

    class Meta:
        model = Equipment
        fields = ["id", "code", "name", "category", "make_model", "reg_no", "ownership", "hire_rate", "supplier",
                  "status", "site", "site_name", "project", "project_name", "service_every_days", "next_service_due",
                  "service_overdue", "notes", "allocations", "maintenance", "created_at"]
        read_only_fields = ["status", "site", "project"]      # changed only by allocate / release / maintenance

    def validate_code(self, v):
        return v.strip().upper()

    def validate(self, attrs):
        if attrs.get("hire_rate") is not None and attrs["hire_rate"] < 0:
            raise serializers.ValidationError({"hire_rate": "Can’t be negative."})
        return attrs
