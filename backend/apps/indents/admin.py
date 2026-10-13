from django.contrib import admin

from .models import Indent, IndentEvent, WorkflowSettings


class EventInline(admin.TabularInline):
    model = IndentEvent
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in IndentEvent._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Indent)
class IndentAdmin(admin.ModelAdmin):
    list_display = ["number", "site", "item", "qty", "status", "stage", "pstatus", "created_at"]
    list_filter = ["status", "stage", "site"]
    search_fields = ["number", "item", "po_no"]
    readonly_fields = ["status", "stage", "pstatus", "pstage", "approved_qty", "issued_qty", "purchase_qty",
                       "received_qty", "balance_cancelled", "held_from", "closed_at", "pclosed_at"]
    inlines = [EventInline]


admin.site.register(WorkflowSettings)
