from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Department, Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["label", "key", "builtin", "all_sites", "active"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["name"]
    list_display = ["name", "mobile", "role", "is_active"]
    list_filter = ["role", "is_active"]
    search_fields = ["name", "mobile", "email"]
    filter_horizontal = ["sites", "extra_roles"]
    fieldsets = [
        (None, {"fields": ["mobile", "password"]}),
        ("Person", {"fields": ["name", "email", "employee_id", "designation", "department", "reporting_manager"]}),
        ("Access", {"fields": ["role", "extra_roles", "sites", "must_change_password"]}),
        ("Alerts", {"fields": ["alert_whatsapp", "alert_email", "alert_sms"]}),
        ("Status", {"fields": ["is_active", "is_staff", "is_superuser"]}),
    ]
    add_fieldsets = [(None, {"classes": ["wide"], "fields": ["mobile", "name", "role", "password1", "password2"]})]


admin.site.register(Department)
