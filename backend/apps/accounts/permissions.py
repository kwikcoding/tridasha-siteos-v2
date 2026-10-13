from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    message = "Only the administrator can do this."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


def module_permission(module: str):
    """Read needs the module in the role's `view` list; writes need it in `edit`."""
    class ModulePermission(permissions.BasePermission):
        message = f"Your role doesn’t have access to {module}."

        def has_permission(self, request, view):
            u = request.user
            if not (u and u.is_authenticated):
                return False
            if request.method in permissions.SAFE_METHODS:
                return u.can_view(module)
            return u.can_edit(module)

    ModulePermission.__name__ = f"Module_{module}"
    return ModulePermission
