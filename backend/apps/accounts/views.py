from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db.models import ProtectedError
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from apps.audit.log import diff, record

from . import perms
from .models import Department, Role, User, normalize_mobile
from .permissions import IsAdmin
from .serializers import (ChangePasswordSerializer, DepartmentSerializer, LoginSerializer, MeSerializer,
                          ResetPasswordSerializer, RoleSerializer, UserSerializer)


class LoginThrottle(SimpleRateThrottle):
    """10 login attempts a minute per IP address."""
    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def _mask(mobile):
    m = normalize_mobile(mobile)
    return (m[:2] + "••••" + m[-4:]) if len(m) == 10 else "••••"


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
@ensure_csrf_cookie
def csrf(request):
    """Sets the csrftoken cookie; the frontend sends it back as X-CSRFToken."""
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([LoginThrottle])
def login_view(request):
    # DRF checks CSRF only for requests that are already signed in; sign-in itself must be checked too,
    # otherwise another website could sign a visitor into an account it controls ("login CSRF").
    check = CSRFCheck(lambda r: None)
    check.process_request(request._request)
    if check.process_view(request._request, None, (), {}) is not None:
        raise PermissionDenied("Security check failed — reload the page and sign in again.")
    ser = LoginSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    mobile = normalize_mobile(ser.validated_data["mobile"])
    user = authenticate(request, mobile=mobile, password=ser.validated_data["password"])
    if not user:
        known = User.objects.filter(mobile=mobile).first()
        record("login.failed", target=known, target_type="user", summary=f"Failed sign-in for {_mask(mobile)}",
               request=request)
        return Response({"detail": "Wrong mobile number or password."}, status=status.HTTP_400_BAD_REQUEST)
    login(request, user)
    record("login.success", actor=user, target=user, summary=f"{user.name} signed in", request=request)
    return Response(MeSerializer(user).data)




@api_view(["POST"])
def logout_view(request):
    record("logout", actor=request.user, target=request.user, summary=f"{request.user.name} signed out", request=request)
    logout(request)
    return Response({"ok": True})


@api_view(["GET"])
def me(request):
    return Response(MeSerializer(request.user).data)


@api_view(["POST"])
def change_password(request):
    ser = ChangePasswordSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    u = request.user
    if not u.check_password(ser.validated_data["current"]):
        raise ValidationError({"current": "Current password is wrong."})
    if ser.validated_data["current"] == ser.validated_data["new"]:
        raise ValidationError({"new": "Choose a password different from the current one."})
    u.set_password(ser.validated_data["new"])
    u.must_change_password = False
    u.save(update_fields=["password", "must_change_password"])
    update_session_auth_hash(request, u)
    record("password.change", actor=u, target=u, summary=f"{u.name} changed their password", request=request)
    return Response(MeSerializer(u).data)


@api_view(["GET"])
def pending(request):
    """Counts for the badges and the dashboard: what is waiting for me."""
    from apps.indents import workflow as wf
    from apps.indents.models import Indent, WorkflowSettings
    u = request.user
    out = {"indents": 0, "purchases": 0, "low_stock": 0, "raised_open": 0}
    if u.can_view("indents"):
        cfg = WorkflowSettings.load().cfg()
        who = u.as_who()
        qs = Indent.objects.exclude(status__in=list(wf.FINAL), pstage__in=["", "closed"]).prefetch_related("history")
        if not u.all_sites:
            qs = qs.filter(site__in=u.site_ids()) | qs.filter(raised_by=u)
        for i in qs.distinct():
            d = i.as_engine_dict([{"action": e.action, "by": e.by_id} for e in i.history.all()])
            acts = wf.allowed_actions(d, who, cfg)
            if any(a in wf.PURCHASE_ACTIONS for a in acts):
                out["purchases"] += 1
            if any(a not in wf.PURCHASE_ACTIONS for a in acts):
                out["indents"] += 1
        out["raised_open"] = Indent.objects.filter(raised_by=u).exclude(status__in=list(wf.FINAL)).count()
    if u.can_view("materials"):
        from apps.materials.services import low_stock_count
        out["low_stock"] = low_stock_count(u)
    out.update(_module_counts(u))
    out["total"] = out["indents"] + out["purchases"]
    return Response(out)


def _module_counts(u):
    """Dashboard counts for the site-work modules — only for modules the role can see."""
    from django.utils import timezone
    today = timezone.localdate()
    ids = None if u.all_sites else u.site_ids()

    def scoped(qs):
        return qs if ids is None else qs.filter(site__in=ids)
    out = {}
    if u.can_view("tasks"):
        from apps.sitework.models import Task
        mine = Task.objects.filter(assignee=u).exclude(status__in=Task.CLOSED)
        out["tasks_mine"] = mine.count()
        out["tasks_overdue"] = scoped(Task.objects.exclude(status__in=Task.CLOSED).filter(due_date__lt=today)).count()
    if u.has_code("dpr.approve"):
        from apps.sitework.models import DailyReport
        out["dpr_to_approve"] = scoped(DailyReport.objects.filter(status="submitted")).exclude(created_by=u).count()
    if u.can_view("dpr"):
        from apps.sitework.models import DailyReport
        out["dpr_today"] = scoped(DailyReport.objects.filter(date=today)).count()
    if u.can_view("labour"):
        from apps.sitework.models import Attendance
        out["present_today"] = scoped(Attendance.objects.filter(date=today, status__in=["present", "half"])).count()
    if u.has_code("expenses.approve"):
        from apps.finance.models import Expense
        out["bills_to_approve"] = scoped(Expense.objects.filter(status="submitted")).exclude(created_by=u).count()
    if u.has_code("expenses.edit"):
        from apps.finance.models import Expense
        out["bills_to_pay"] = scoped(Expense.objects.filter(status__in=["approved", "part_paid"])).exclude(
            approved_by=u).count()
    if u.can_view("quality"):
        from apps.compliance.models import Observation
        out["observations_open"] = scoped(Observation.objects.exclude(status="closed")).count()
        out["observations_mine"] = Observation.objects.filter(assigned_to=u).exclude(status="closed").count()
    if u.can_view("equipment"):
        from apps.plant.models import Equipment
        out["equipment_service_due"] = Equipment.objects.filter(next_service_due__lte=today).exclude(
            status="disposed").count()
    return out


@api_view(["GET"])
def people(request):
    """Names for pickers (assign a task, an observation, a project head): active staff on a site."""
    qs = User.objects.filter(is_active=True).select_related("department").prefetch_related("sites", "role", "extra_roles")
    try:
        site = int(request.query_params.get("site") or 0)
    except ValueError:
        site = 0
    out = []
    for u in qs.order_by("name"):
        if site and not (u.all_sites or site in u.site_ids()):
            continue
        out.append({"id": u.id, "name": u.name, "designation": u.designation,
                    "department": u.department.name if u.department else ""})
    return Response(out)


@api_view(["GET"])
def permission_catalogue(request):
    from apps.indents.workflow import STAGES
    return Response({
        "modules": perms.catalogue(),
        "steps": [{"key": s.key, "n": s.n, "short": s.short, "dept": s.dept, "lane": s.lane, "actions": list(s.actions)}
                  for s in STAGES],
    })


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related("head")
    serializer_class = DepartmentSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def perform_create(self, ser):
        d = ser.save()
        record("department.create", actor=self.request.user, target=d, summary=f"Department {d.name} added",
               request=self.request)

    def perform_update(self, ser):
        changes = diff(ser.instance, ser.validated_data)
        d = ser.save()
        record("department.update", actor=self.request.user, target=d, summary=f"Department {d.name} changed",
               changes=changes, request=self.request)


class UserViewSet(viewsets.ModelViewSet):
    """Team: the administrator creates a separate login for each person and gives them roles."""
    queryset = User.objects.select_related("role", "department", "reporting_manager").prefetch_related("sites", "extra_roles")
    serializer_class = UserSerializer
    search_fields = ["name", "mobile", "email", "employee_id", "designation"]
    filterset_fields = ["role", "is_active", "department"]
    http_method_names = ["get", "post", "patch", "head", "options"]   # deactivate instead of delete

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            from .permissions import module_permission
            return [permissions.IsAuthenticated(), module_permission("team")()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def perform_create(self, ser):
        u = ser.save()
        record("user.create", actor=self.request.user, target=u, summary=f"Login created for {u.name}",
               changes={k: v for k, v in ser.validated_data.items() if k != "password"}, request=self.request)

    def perform_update(self, ser):
        changes = diff(ser.instance, {k: v for k, v in ser.validated_data.items() if k != "password"})
        u = ser.save()
        if changes:
            what = "deactivated" if changes.get("is_active", [None, True])[1] is False else "changed"
            record("user.update", actor=self.request.user, target=u, summary=f"{u.name} {what}", changes=changes,
                   request=self.request)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        """Administrator sets a temporary password; the person must change it at their next sign-in."""
        u = self.get_object()
        ser = ResetPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        u.set_password(ser.validated_data["password"])
        u.must_change_password = u.pk != request.user.pk
        u.save(update_fields=["password", "must_change_password"])
        if u.pk == request.user.pk:
            update_session_auth_hash(request, u)
        record("password.reset", actor=request.user, target=u, summary=f"Password reset for {u.name}", request=request)
        return Response(UserSerializer(u, context={"request": request}).data)


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    pagination_class = None

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def perform_create(self, ser):
        r = ser.save()
        record("role.create", actor=self.request.user, target=r, summary=f"Role {r.label} created",
               changes=ser.validated_data, request=self.request)

    def perform_update(self, ser):
        changes = diff(ser.instance, ser.validated_data)
        r = ser.save()
        if changes:
            record("role.update", actor=self.request.user, target=r, summary=f"Role {r.label} changed", changes=changes,
                   request=self.request)

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.builtin:
            raise ValidationError({"detail": "Built-in roles can’t be deleted — switch their steps off instead."})
        if role.extra_users.exists():
            raise ValidationError({"detail": "People still have this role. Give them another role first."})
        try:
            role.delete()
        except ProtectedError:
            raise ValidationError({"detail": "People still have this role. Give them another role first."})
        record("role.delete", actor=request.user, target_type="role", target_id=str(kwargs.get("pk")),
               summary=f"Role {role.label} deleted", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
