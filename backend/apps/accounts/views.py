from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db.models import ProtectedError
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from .models import Role, User, normalize_mobile
from .permissions import IsAdmin
from .serializers import ChangePasswordSerializer, LoginSerializer, MeSerializer, RoleSerializer, UserSerializer


class LoginThrottle(SimpleRateThrottle):
    """10 login attempts a minute per IP address."""
    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


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
    ser = LoginSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user = authenticate(request, mobile=normalize_mobile(ser.validated_data["mobile"]),
                        password=ser.validated_data["password"])
    if not user:
        return Response({"detail": "Wrong mobile number or password."}, status=status.HTTP_400_BAD_REQUEST)
    login(request, user)
    return Response(MeSerializer(user).data)


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"ok": True})


@api_view(["GET"])
def me(request):
    return Response(MeSerializer(request.user).data)


@api_view(["POST"])
def change_password(request):
    ser = ChangePasswordSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    if not request.user.check_password(ser.validated_data["current"]):
        raise ValidationError({"current": "Current password is wrong."})
    request.user.set_password(ser.validated_data["new"])
    request.user.save(update_fields=["password"])
    update_session_auth_hash(request, request.user)
    return Response({"ok": True})


class UserViewSet(viewsets.ModelViewSet):
    """Team: the administrator creates a separate login for each person and gives them a role."""
    queryset = User.objects.select_related("role").prefetch_related("sites")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]
    search_fields = ["name", "mobile", "email"]
    filterset_fields = ["role", "is_active"]
    http_method_names = ["get", "post", "patch", "head", "options"]   # deactivate instead of delete


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    pagination_class = None

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdmin()]

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.builtin:
            raise ValidationError({"detail": "Built-in roles can’t be deleted — switch their steps off instead."})
        try:
            role.delete()
        except ProtectedError:
            raise ValidationError({"detail": "People still have this role. Give them another role first."})
        return Response(status=status.HTTP_204_NO_CONTENT)
