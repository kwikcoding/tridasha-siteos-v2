from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts import views as acc
from apps.alerts.views import NotificationViewSet
from apps.indents import views as ind
from apps.materials import views as mat
from apps.sites.views import SiteViewSet

router = DefaultRouter()
router.register("users", acc.UserViewSet, basename="user")
router.register("roles", acc.RoleViewSet, basename="role")
router.register("sites", SiteViewSet, basename="site")
router.register("indents", ind.IndentViewSet, basename="indent")
router.register("materials", mat.MaterialViewSet, basename="material")
router.register("register", mat.RegisterViewSet, basename="register")
router.register("stock", mat.StockViewSet, basename="stock")
router.register("notifications", NotificationViewSet, basename="notification")

api = [
    path("auth/csrf/", acc.csrf),
    path("auth/login/", acc.login_view),
    path("auth/logout/", acc.logout_view),
    path("auth/me/", acc.me),
    path("auth/password/", acc.change_password),
    path("workflow/", ind.workflow_meta),
    path("workflow/settings/", ind.workflow_settings),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("", include(router.urls)),
]

urlpatterns = [
    path("api/health/", lambda r: JsonResponse({"ok": True})),
    path("api/", include(api)),
    path("django-admin/", admin.site.urls),
]
