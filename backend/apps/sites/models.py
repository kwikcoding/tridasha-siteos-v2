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
