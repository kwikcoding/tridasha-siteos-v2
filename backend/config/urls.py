from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts import views as acc
from apps.alerts.views import NotificationViewSet
from apps.audit.views import AuditViewSet
from apps.legacy import views as legacy
from apps.indents import views as ind
from apps.materials import views as mat
from apps.core import company
from apps.compliance.views import DocumentViewSet, ObservationViewSet
from apps.finance.views import ExpenseViewSet
from apps.plant.views import EquipmentViewSet
from apps.reports import views as reports
from apps.sites.views import ProjectViewSet, SiteViewSet
from apps.sitework.views import AttendanceViewSet, DailyReportViewSet, TaskViewSet, WorkerViewSet

router = DefaultRouter()
router.register("users", acc.UserViewSet, basename="user")
router.register("roles", acc.RoleViewSet, basename="role")
router.register("departments", acc.DepartmentViewSet, basename="department")
router.register("audit", AuditViewSet, basename="audit")
router.register("legacy/records", legacy.V1RecordViewSet, basename="v1record")
router.register("sites", SiteViewSet, basename="site")
router.register("indents", ind.IndentViewSet, basename="indent")
router.register("materials", mat.MaterialViewSet, basename="material")
router.register("register", mat.RegisterViewSet, basename="register")
router.register("stock", mat.StockViewSet, basename="stock")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("projects", ProjectViewSet, basename="project")
router.register("tasks", TaskViewSet, basename="task")
router.register("dpr", DailyReportViewSet, basename="dpr")
router.register("workers", WorkerViewSet, basename="worker")
router.register("attendance", AttendanceViewSet, basename="attendance")
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("observations", ObservationViewSet, basename="observation")
router.register("documents", DocumentViewSet, basename="document")
router.register("equipment", EquipmentViewSet, basename="equipment")

api = [
    path("auth/csrf/", acc.csrf),
    path("auth/login/", acc.login_view),
    path("auth/logout/", acc.logout_view),
    path("auth/me/", acc.me),
    path("auth/password/", acc.change_password),
    path("auth/pending/", acc.pending),
    path("people/", acc.people),
    path("company/", company.company),
    path("company/logo/", company.company_logo),
    path("permissions/", acc.permission_catalogue),
    path("legacy/import/", legacy.import_v1),
    path("legacy/demo/", legacy.demo_data),
    path("workflow/", ind.workflow_meta),
    path("workflow/settings/", ind.workflow_settings),
    path("reports/summary/", reports.summary),
    path("reports/export/", reports.export),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("", include(router.urls)),
]

urlpatterns = [
    path("api/health/", lambda r: JsonResponse({"ok": True})),
    path("api/", include(api)),
    path("django-admin/", admin.site.urls),
]
