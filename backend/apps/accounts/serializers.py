from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Role, User, normalize_mobile, validate_mobile
from .roles import ADMIN_MODULES, STAGE_KEYS, WORK_MODULES


class RoleSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Role
        fields = ["id", "key", "label", "description", "color", "view", "edit", "stages", "can_approve", "all_sites",
                  "builtin", "active", "user_count"]
        read_only_fields = ["builtin"]

    def _list(self, value, allowed, name):
        if not isinstance(value, list) or any(v not in allowed for v in value):
            raise serializers.ValidationError(f"Unknown {name}.")
        return list(dict.fromkeys(value))

    def validate_key(self, value):
        if self.instance and value != self.instance.key:
            raise serializers.ValidationError("A role’s key can’t be changed.")
        return value

    def validate(self, attrs):
        inst = self.instance
        if inst and inst.key == "admin":
            raise serializers.ValidationError("The Administrator role can’t be changed.")
        mods = WORK_MODULES  # team/settings stay admin-only
        view = self._list(attrs.get("view", inst.view if inst else []), mods, "module")
        edit = [m for m in self._list(attrs.get("edit", inst.edit if inst else []), mods, "module") if m in view]
        stages = self._list(attrs.get("stages", inst.stages if inst else []), STAGE_KEYS, "step")
        if stages:   # people who act on indents must see and edit them
            view = list(dict.fromkeys(view + ["indents"]))
            edit = list(dict.fromkeys(edit + ["indents"]))
        attrs.update(view=view, edit=edit, stages=stages)
        return attrs


class UserSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source="role.label", read_only=True, default="")
    role_key = serializers.CharField(source="role.key", read_only=True, default="")
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, min_length=8)

    class Meta:
        model = User
        fields = ["id", "mobile", "name", "email", "role", "role_key", "role_label", "sites", "is_active",
                  "alert_whatsapp", "alert_email", "alert_sms", "date_joined", "last_login", "password"]
        read_only_fields = ["date_joined", "last_login"]

    def validate_mobile(self, value):
        value = normalize_mobile(value)
        validate_mobile(value)
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Set a password for the new login."})
        req = self.context.get("request")
        if self.instance and req and self.instance.pk == req.user.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError("You can’t deactivate your own login.")
            if "role" in attrs and attrs["role"] != self.instance.role:
                raise serializers.ValidationError("You can’t change your own role.")
        return attrs

    def create(self, validated):
        sites = validated.pop("sites", [])
        password = validated.pop("password")
        user = User.objects.create_user(password=password, **validated)
        user.sites.set(sites)
        return user

    def update(self, inst, validated):
        password = validated.pop("password", None)
        user = super().update(inst, validated)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class MeSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    is_admin = serializers.BooleanField(read_only=True)
    modules_view = serializers.SerializerMethodField()
    modules_edit = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "mobile", "name", "email", "role", "is_admin", "sites", "modules_view", "modules_edit",
                  "alert_whatsapp", "alert_email", "alert_sms"]

    def get_modules_view(self, u):
        return WORK_MODULES + ADMIN_MODULES if u.is_admin else list(u.role.view if u.role else [])

    def get_modules_edit(self, u):
        return WORK_MODULES + ADMIN_MODULES if u.is_admin else list(u.role.edit if u.role else [])


class LoginSerializer(serializers.Serializer):
    mobile = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    current = serializers.CharField(trim_whitespace=False)
    new = serializers.CharField(trim_whitespace=False, min_length=8)

    def validate_new(self, value):
        validate_password(value)
        return value
