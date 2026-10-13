import re

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


def normalize_mobile(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def validate_mobile(value: str):
    if not MOBILE_RE.match(normalize_mobile(value)):
        raise ValidationError("Enter a 10-digit Indian mobile number.")


class Department(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=20, blank=True)
    head = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Role(models.Model):
    """A job role. Decides which modules a person sees/edits and which workflow steps they act on."""
    key = models.SlugField(max_length=30, unique=True)
    label = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)
    color = models.CharField(max_length=20, default="slate")
    permissions = models.JSONField(default=list, blank=True)   # permission codes, see perms.py
    view = models.JSONField(default=list, blank=True)      # module keys — kept in step with `permissions`
    edit = models.JSONField(default=list, blank=True)      # module keys — kept in step with `permissions`
    stages = models.JSONField(default=list, blank=True)    # workflow stage keys
    step_actions = models.JSONField(default=dict, blank=True)  # optional {stage: [actions]} limit within a step
    can_approve = models.BooleanField(default=False)
    all_sites = models.BooleanField(default=False)
    builtin = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        from .perms import view_edit_from_codes
        self.view, self.edit = view_edit_from_codes(self.permissions or [])
        super().save(*args, **kwargs)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, mobile, password=None, **extra):
        mobile = normalize_mobile(mobile)
        validate_mobile(mobile)
        user = self.model(mobile=mobile, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if "role" not in extra:
            extra["role"] = Role.objects.filter(key="admin").first()
        return self.create_user(mobile, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    mobile = models.CharField(max_length=10, unique=True, validators=[validate_mobile])
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.PROTECT, related_name="users")  # primary role
    extra_roles = models.ManyToManyField(Role, blank=True, related_name="extra_users")
    sites = models.ManyToManyField("sites.Site", blank=True, related_name="members")
    # staff details
    employee_id = models.CharField(max_length=30, unique=True, null=True, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="staff")
    reporting_manager = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reports")
    must_change_password = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)   # Django admin access only
    date_joined = models.DateTimeField(default=timezone.now)
    # alert preferences
    alert_whatsapp = models.BooleanField(default=True)
    alert_email = models.BooleanField(default=False)
    alert_sms = models.BooleanField(default=False)

    objects = UserManager()
    USERNAME_FIELD = "mobile"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.mobile})"

    # ---------------------------------------------------------------- effective access
    def all_roles(self) -> list:
        cache = getattr(self, "_roles_cache", None)
        if cache is None:
            cache = [r for r in ([self.role] if self.role_id else []) if r.active]
            if self.pk:
                cache += [r for r in self.extra_roles.all() if r.active and r.pk != self.role_id]
            self._roles_cache = cache
        return cache

    @property
    def is_admin(self) -> bool:
        return self.is_superuser or any(r.key == "admin" for r in self.all_roles())

    @property
    def perm_codes(self) -> set:
        from .perms import ALL_CODES
        if self.is_admin:
            return set(ALL_CODES)
        return {c for r in self.all_roles() for c in (r.permissions or [])}

    def has_code(self, code: str) -> bool:
        return self.is_active and code in self.perm_codes

    @property
    def stage_keys(self) -> list:
        return sorted({s for r in self.all_roles() for s in (r.stages or [])})

    def step_action_limits(self) -> dict:
        """{stage: set(actions)} only for stages where EVERY role granting it limits the actions."""
        limits = {}
        for st in self.stage_keys:
            allowed, unlimited = set(), False
            for r in self.all_roles():
                if st not in (r.stages or []):
                    continue
                lim = (r.step_actions or {}).get(st)
                if lim is None:
                    unlimited = True
                else:
                    allowed |= set(lim)
            if not unlimited:
                limits[st] = sorted(allowed)
        return limits

    def as_who(self) -> dict:
        """The shape the workflow engine expects."""
        return {"id": self.pk, "admin": self.is_admin, "stages": self.stage_keys, "limits": self.step_action_limits()}

    def can_view(self, module: str) -> bool:
        return self.has_code(f"{module}.view")

    def can_edit(self, module: str) -> bool:
        return self.has_code(f"{module}.create") or self.has_code(f"{module}.edit")

    @property
    def all_sites(self) -> bool:
        return self.is_admin or any(r.all_sites for r in self.all_roles())

    def site_ids(self):
        return set(self.sites.values_list("id", flat=True))
