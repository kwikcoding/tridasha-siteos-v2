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


class Role(models.Model):
    """A job role. Decides which modules a person sees/edits and which workflow steps they act on."""
    key = models.SlugField(max_length=30, unique=True)
    label = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)
    color = models.CharField(max_length=20, default="slate")
    view = models.JSONField(default=list, blank=True)      # module keys
    edit = models.JSONField(default=list, blank=True)      # module keys (subset of view)
    stages = models.JSONField(default=list, blank=True)    # workflow stage keys
    can_approve = models.BooleanField(default=False)
    all_sites = models.BooleanField(default=False)
    builtin = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label


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
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.PROTECT, related_name="users")
    sites = models.ManyToManyField("sites.Site", blank=True, related_name="members")
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

    @property
    def is_admin(self) -> bool:
        return self.is_superuser or bool(self.role and self.role.key == "admin")

    @property
    def stage_keys(self) -> list:
        return list(self.role.stages) if self.role else []

    def as_who(self) -> dict:
        """The shape the workflow engine expects."""
        return {"id": self.pk, "admin": self.is_admin, "stages": self.stage_keys}

    def can_view(self, module: str) -> bool:
        return self.is_admin or bool(self.role and module in (self.role.view or []))

    def can_edit(self, module: str) -> bool:
        return self.is_admin or bool(self.role and module in (self.role.edit or []))

    @property
    def all_sites(self) -> bool:
        return self.is_admin or bool(self.role and self.role.all_sites)

    def site_ids(self):
        return set(self.sites.values_list("id", flat=True))
