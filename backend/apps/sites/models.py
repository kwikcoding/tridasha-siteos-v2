from django.db import models


class Site(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    address = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Project(models.Model):
    """A piece of work at a site — a tower, a block, the clubhouse, an infrastructure package."""
    STATUS = [("planned", "Planned"), ("active", "Active"), ("on_hold", "On hold"), ("completed", "Completed")]

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="projects")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=12, choices=STATUS, default="active", db_index=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    head = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="projects_led")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["site__name", "code"]
        constraints = [models.UniqueConstraint(fields=["site", "code"], name="project_code_per_site")]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def is_open(self):
        return self.status in ("planned", "active", "on_hold")
