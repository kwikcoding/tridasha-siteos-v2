from django.contrib import admin

from .models import Material, RegisterItem, StockEntry


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "category", "unit", "std_rate", "active"]
    list_filter = ["category", "active"]
    search_fields = ["code", "name"]


@admin.register(RegisterItem)
class RegisterItemAdmin(admin.ModelAdmin):
    list_display = ["item_id", "trade", "item", "applicability", "status"]
    list_filter = ["trade", "applicability", "status"]
    search_fields = ["item_id", "item"]


@admin.register(StockEntry)
class StockEntryAdmin(admin.ModelAdmin):
    list_display = ["date", "site", "material", "kind", "qty", "source", "ref"]
    list_filter = ["site", "kind", "source"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
