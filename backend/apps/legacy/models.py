from django.db import models


class V1Record(models.Model):
    """Every row from the v1 spreadsheets, kept as-is. Sections not built in v2 yet (bills, labour, DPR, tasks,
    quality, equipment, old indents) are imported from here when they arrive — nothing is lost."""
    tab = models.CharField(max_length=80, db_index=True)       # e.g. "Labour"
    key = models.CharField(max_length=64)                       # stable hash of the row
    row_no = models.PositiveIntegerField(default=0)
    data = models.JSONField(default=dict)                       # {header: value}
    source_file = models.CharField(max_length=200, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tab", "row_no"]
        constraints = [models.UniqueConstraint(fields=["tab", "key"], name="v1record_tab_key")]
