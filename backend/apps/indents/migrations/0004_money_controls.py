from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive only: three nullable money columns on Indent and the step-11 tolerance setting."""

    dependencies = [("indents", "0003_indentevent_override")]

    operations = [
        migrations.AddField("indent", "inv_expected",
                            models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
        migrations.AddField("indent", "pay_auth_amount",
                            models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
        migrations.AddField("indent", "paid_total",
                            models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
        migrations.AddField("workflowsettings", "inv_tolerance_pct",
                            models.DecimalField(decimal_places=2, default=Decimal("1.00"), max_digits=5)),
    ]
