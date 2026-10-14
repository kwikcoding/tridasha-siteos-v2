from rest_framework import serializers

from .models import Material, RegisterItem, StockEntry


class MaterialSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, required=False)

    class Meta:
        model = Material
        fields = ["id", "code", "name", "category", "unit", "spec", "hsn", "gst_rate", "std_rate", "reorder_level",
                  "active", "balance", "updated_at"]

    def validate_code(self, v):
        v = v.strip().upper()
        if self.instance and v != self.instance.code and self.instance.stock_entries.exists():
            raise serializers.ValidationError("This item has stock entries — its code can’t change.")
        return v


class RegisterItemSerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source="material.code", read_only=True, default="")
    material_name = serializers.CharField(source="material.name", read_only=True, default="")

    class Meta:
        model = RegisterItem
        fields = ["id", "item_id", "trade", "system", "item", "unit", "spec", "applicability", "zone", "req_qty", "grade",
                  "make", "vendor", "boq_ref", "status", "required_by", "remarks", "material", "material_code",
                  "material_name", "updated_at"]

    def validate_item_id(self, v):
        return v.strip().upper()


class StockEntrySerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source="material.code", read_only=True)
    material_name = serializers.CharField(source="material.name", read_only=True)
    unit = serializers.CharField(source="material.unit", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)
    by_name = serializers.CharField(source="by.name", read_only=True)
    indent_number = serializers.CharField(source="indent.number", read_only=True, default="")

    class Meta:
        model = StockEntry
        fields = ["id", "site", "site_name", "project", "material", "material_code", "material_name", "unit", "date", "kind", "qty",
                  "rate", "source", "indent", "indent_number", "ref", "party", "note", "by_name", "created_at"]
        read_only_fields = ["indent", "created_at"]


class StockEntryCreateSerializer(serializers.Serializer):
    site = serializers.IntegerField()
    project = serializers.IntegerField(required=False, allow_null=True)
    material = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=["IN", "OUT", "ADJ"])
    qty = serializers.DecimalField(max_digits=14, decimal_places=3)
    date = serializers.DateField(required=False)
    rate = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    source = serializers.ChoiceField(choices=["opening", "purchase", "transfer", "return", "adjust", "manual"],
                                     default="manual")
    ref = serializers.CharField(required=False, allow_blank=True, max_length=80)
    party = serializers.CharField(required=False, allow_blank=True, max_length=150)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ImportSerializer(serializers.Serializer):
    file = serializers.FileField()
    commit = serializers.BooleanField(default=False)
