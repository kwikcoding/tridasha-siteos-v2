from django.contrib import admin

from .models import V1Record


@admin.register(V1Record)
class V1RecordAdmin(admin.ModelAdmin):
    list_display = ["tab", "row_no", "source_file", "imported_at"]
    list_filter = ["tab"]
