from django.http import JsonResponse
from rest_framework import permissions

METHOD_VERB = {"GET": "view", "HEAD": "view", "OPTIONS": "view", "POST": "create", "PUT": "edit", "PATCH": "edit",
               "DELETE": "delete"}


class IsAdmin(permissions.BasePermission):
    message = "Only the administrator can do this."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


def module_permission(module: str, **action_codes):
    """Server-side check of the role's permission codes.

    By default GET needs '<module>.view', POST '<module>.create', PATCH '<module>.edit', DELETE '<module>.delete'.
    Extra actions are mapped by name, e.g. module_permission("materials", import_file="materials.import").
    """
    class ModulePermission(permissions.BasePermission):
        def has_permission(self, request, view):
            u = request.user
            if not (u and u.is_authenticated):
                return False
            code = action_codes.get(getattr(view, "action", None) or "") or f"{module}.{METHOD_VERB.get(request.method, 'edit')}"
            self.message = "Your role doesn’t allow this (" + code + ")."
            return u.has_code(code)

    ModulePermission.__name__ = f"Module_{module}"
    return ModulePermission


class PasswordChangeMiddleware:
    """After an administrator resets a password, the person must set their own before using anything else."""
    ALLOWED = ("/api/auth/",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = getattr(request, "user", None)
        if (u is not None and u.is_authenticated and getattr(u, "must_change_password", False)
                and request.path.startswith("/api/") and not request.path.startswith(self.ALLOWED)):
            return JsonResponse({"detail": "Please set a new password first.", "code": "password_change_required"},
                                status=403)
        return self.get_response(request)
