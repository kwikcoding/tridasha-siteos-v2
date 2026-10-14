import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.core.models


class Migration(migrations.Migration):
    """Additive: the single-row company profile."""

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Tridasha", max_length=150)),
                ("legal_name", models.CharField(blank=True, max_length=200)),
                ("gstin", models.CharField(blank=True, max_length=15)),
                ("pan", models.CharField(blank=True, max_length=10)),
                ("cin", models.CharField(blank=True, max_length=21)),
                ("address", models.TextField(blank=True)),
                ("city", models.CharField(blank=True, max_length=80)),
                ("state", models.CharField(blank=True, max_length=80)),
                ("pincode", models.CharField(blank=True, max_length=6)),
                ("phone", models.CharField(blank=True, max_length=20)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("website", models.URLField(blank=True)),
                ("financial_year_start", models.PositiveSmallIntegerField(choices=[(1, "January"), (2, "February"), (3, "March"), (4, "April"), (5, "May"), (6, "June"), (7, "July"), (8, "August"), (9, "September"), (10, "October"), (11, "November"), (12, "December")], default=4)),
                ("logo", models.FileField(blank=True, upload_to=apps.core.models.logo_upload_to)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
