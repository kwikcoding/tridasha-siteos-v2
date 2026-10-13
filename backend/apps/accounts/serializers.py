from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.indents.workflow import STAGE

from . import perms
from .models import Department, Role, User, normalize_mobile, validate_mobile


class DepartmentSerializer(serializers.ModelSerializer):
    head_name = serializers.CharField(source="head.name", read_only=True, default="")
    staff_count = serializers.IntegerField(source="staff.count", read_only=True)

    class Meta:
        model = Department
        fields = ["id", "name", "code", "head", "head_name", "active", "staff_count"]


class RoleSerializer(serializers.ModelSerializer):
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "key", "label", "description", "color", "permissions", "view", "edit", "stages", "step_actions",
                  "can_approve", "all_sites", "builtin", "active", "user_count"]
        read_only_fields = ["builtin", "view", "edit"]

    def get_user_count(self, r):
        return User.objects.filter(is_active=True).filter(
            models_q_role(r)).distinct().count()

    def validate_key(self, value):
        if self.instance and value != self.instance.key:
            raise serializers.ValidationError("A role’s key can’t be changed.")
        return value

    def validate(self, attrs):
        inst = self.instance
        if inst and inst.key == "admin":
            raise serializers.ValidationError("The Administrator role can’t be changed.")
        if not inst and attrs.get("key") == "admin":
            raise serializers.ValidationError({"key": "That key is reserved."})
        codes = attrs.get("permissions", inst.permissions if inst else [])
        if not isinstance(codes, list):
            raise serializers.ValidationError({"permissions": "Must be a list."})
        bad = [c for c in codes if c in perms.ADMIN_ONLY_CODES]
        if bad:
            raise serializers.ValidationError({"permissions": f"Only the Administrator can have {', '.join(bad)}."})
        unknown = [c for c in codes if c not in perms.ALL_CODES]
        if unknown:
            raise serializers.ValidationError({"permissions": f"Unknown permission {', '.join(unknown)}."})
        stages = attrs.get("stages", inst.stages if inst else [])
        if not isinstance(stages, list) or any(s not in STAGE for s in stages):
            raise serializers.ValidationError({"stages": "Unknown step."})
        stages = list(dict.fromkeys(stages))
        limits = attrs.get("step_actions", inst.step_actions if inst else {}) or {}
        if not isinstance(limits, dict):
            raise serializers.ValidationError({"step_actions": "Must be an object."})
        clean_limits = {}
        for st, acts in limits.items():
            if st not in stages:
                continue           # limits only matter for steps the role has
            if st not in STAGE or not isinstance(acts, list) or any(a not in STAGE[st].actions for a in acts):
                raise serializers.ValidationError({"step_actions": f"Unknown action for step {st}."})
            if set(acts) != set(STAGE[st].actions):   # all actions = no limit
                clean_limits[st] = list(dict.fromkeys(acts))
        codes = perms.clean_codes(codes)
        if stages:               # people who act on indents must see them
            codes = sorted(set(codes) | {"indents.view"})
        attrs.update(permissions=codes, stages=stages, step_actions=clean_limits)
        return attrs


def models_q_role(r):
    from django.db.models import Q
    return Q(role=r) | Q(extra_roles=r)


class UserSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source="role.label", read_only=True, default="")
    role_key = serializers.CharField(source="role.key", read_only=True, default="")
    department_name = serializers.CharField(source="department.name", read_only=True, default="")
    manager_name = serializers.CharField(source="reporting_manager.name", read_only=True, default="")
    all_role_labels = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, min_length=8)

    class Meta:
        model = User
        fields = ["id", "employee_id", "mobile", "name", "email", "designation", "department", "department_name",
                  "reporting_manager", "manager_name", "role", "role_key", "role_label", "extra_roles", "all_role_labels",
                  "sites", "is_active", "must_change_password", "alert_whatsapp", "alert_email", "alert_sms",
                  "date_joined", "last_login", "password"]
        read_only_fields = ["date_joined", "last_login", "must_change_password"]
        extra_kwargs = {"employee_id": {"allow_null": True, "required": False}}

    def get_all_role_labels(self, u):
        return [r.label for r in u.all_roles()]

    def validate_mobile(self, value):
        value = normalize_mobile(value)
        validate_mobile(value)
        return value

    def validate_employee_id(self, value):
        value = (value or "").strip().upper()
        return value or None

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Set a password for the new login."})
        mgr = attrs.get("reporting_manager")
        if self.instance and mgr and mgr.pk == self.instance.pk:
            raise serializers.ValidationError({"reporting_manager": "A person can’t report to themselves."})
        req = self.context.get("request")
        if self.instance and req and self.instance.pk == req.user.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError("You can’t deactivate your own login.")
            if "role" in attrs and attrs["role"] != self.instance.role:
                raise serializers.ValidationError("You can’t change your own role.")
            if "extra_roles" in attrs:
                raise serializers.ValidationError("You can’t change your own roles.")
        return attrs

    def create(self, validated):
        sites = validated.pop("sites", [])
        extra = validated.pop("extra_roles", [])
        password = validated.pop("password")
        user = User.objects.create_user(password=password, must_change_password=True, **validated)
        user.sites.set(sites)
        user.extra_roles.set([r for r in extra if r.pk != user.role_id])
        return user

    def update(self, inst, validated):
        validated.pop("password", None)      # passwords change through reset-password, which is audited
        extra = validated.pop("extra_roles", None)
        user = super().update(inst, validated)
        if extra is not None:
            user.extra_roles.set([r for r in extra if r.pk != user.role_id])
        user.__dict__.pop("_roles_cache", None)
        return user


class MeSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    roles = serializers.SerializerMethodField()
    is_admin = serializers.BooleanField(read_only=True)
    permissions = serializers.SerializerMethodField()
    modules_view = serializers.SerializerMethodField()
    modules_edit = serializers.SerializerMethodField()
    stages = serializers.SerializerMethodField()
    department_name = serializers.CharField(source="department.name", read_only=True, default="")
    manager_name = serializers.CharField(source="reporting_manager.name", read_only=True, default="")

    class Meta:
        model = User
        fields = ["id", "employee_id", "mobile", "name", "email", "designation", "department_name", "manager_name",
                  "role", "roles", "is_admin", "sites", "permissions", "modules_view", "modules_edit", "stages",
                  "must_change_password", "alert_whatsapp", "alert_email", "alert_sms", "last_login"]

    def get_roles(self, u):
        return [{"key": r.key, "label": r.label} for r in u.all_roles()]

    def get_permissions(self, u):
        return sorted(u.perm_codes)

    def get_modules_view(self, u):
        return sorted({c.split(".")[0] for c in u.perm_codes if c.endswith(".view")})

    def get_modules_edit(self, u):
        return sorted({c.split(".")[0] for c in u.perm_codes if c.split(".")[1] in ("create", "edit")})

    def get_stages(self, u):
        return u.stage_keys


class LoginSerializer(serializers.Serializer):
    mobile = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    current = serializers.CharField(trim_whitespace=False)
    new = serializers.CharField(trim_whitespace=False, min_length=8)

    def validate_new(self, value):
        validate_password(value)
        return value


class ResetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False, min_length=8)

    def validate_password(self, value):
        validate_password(value)
        return value
