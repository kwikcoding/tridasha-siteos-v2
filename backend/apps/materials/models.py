from django.conf import settings
from django.db import models
from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce

from .importer import APPLICABILITY, REG_STATUS

QTY = dict(max_digits=14, decimal_places=3)


class Material(models.Model):
    """Catalogue item — what the stores keep and indents ask for."""
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True, db_index=True)
    unit = models.CharField(max_length=20, blank=True)
    spec = models.TextField(blank=True)
    hsn = models.CharField(max_length=20, blank=True)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    std_rate = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    reorder_level = models.DecimalField(**QTY, null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class RegisterItem(models.Model):
    """High-rise materials register — the project's checklist of everything to specify and procure."""
    item_id = models.CharField(max_length=80, unique=True)
    trade = models.CharField(max_length=100, blank=True, db_index=True)
    system = models.CharField(max_length=150, blank=True)
    item = models.CharField(max_length=255)
    unit = models.CharField(max_length=20, blank=True)
    spec = models.TextField(blank=True)
    applicability = models.CharField(max_length=30, choices=[(x, x) for x in APPLICABILITY], default="To review",
                                     db_index=True)
    zone = models.CharField(max_length=150, blank=True)
    req_qty = models.DecimalField(**QTY, null=True, blank=True)
    grade = models.CharField(max_length=150, blank=True)
    make = models.CharField(max_length=150, blank=True)
    vendor = models.CharField(max_length=150, blank=True)
    boq_ref = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=30, choices=[(x, x) for x in REG_STATUS], default="Not started", db_index=True)
    required_by = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    material = models.ForeignKey(Material, null=True, blank=True, on_delete=models.SET_NULL, related_name="register_items")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["item_id"]

    def __str__(self):
        return f"{self.item_id} {self.item}"


class StockEntry(models.Model):
    """Append-only stock ledger per site store. Balance = Σ IN − Σ OUT ± ADJ.
    Mistakes are corrected with an adjustment entry, never by editing or deleting."""
    IN, OUT, ADJ = "IN", "OUT", "ADJ"
    KINDS = [(IN, "Received"), (OUT, "Issued"), (ADJ, "Adjustment")]
    SOURCES = [("opening", "Opening stock"), ("purchase", "Purchase receipt (GRN)"), ("indent-issue", "Issued against indent"),
               ("transfer", "Transfer"), ("return", "Return to supplier"), ("site-return", "Returned to store from site"),
               ("adjust", "Stock count adjustment"), ("manual", "Manual entry"), ("v1", "Imported from SiteOS v1")]

    site = models.ForeignKey("sites.Site", on_delete=models.PROTECT, related_name="stock_entries")
    project = models.ForeignKey("sites.Project", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="stock_entries")   # which project the material went to / came for
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="stock_entries")
    date = models.DateField()
    kind = models.CharField(max_length=3, choices=KINDS)
    qty = models.DecimalField(**QTY)        # always positive for IN / OUT; signed for ADJ
    rate = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=20, choices=SOURCES, default="manual")
    indent = models.ForeignKey("indents.Indent", null=True, blank=True, on_delete=models.PROTECT, related_name="stock_entries")
    ref = models.CharField(max_length=80, blank=True)            # GRN / challan / issue slip number
    party = models.CharField(max_length=150, blank=True)         # supplier or receiving team
    note = models.TextField(blank=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    import_key = models.CharField(max_length=64, null=True, blank=True, unique=True)   # set for rows imported from v1

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["site", "material"])]
        verbose_name_plural = "stock entries"

    @staticmethod
    def signed_qty(prefix: str = ""):
        """+qty for IN / ADJ, −qty for OUT. `prefix` lets other models aggregate through the relation."""
        return Case(When(**{f"{prefix}kind": "OUT"}, then=-F(f"{prefix}qty")), default=F(f"{prefix}qty"),
                    output_field=DecimalField(**QTY))

    @classmethod
    def balance(cls, site_id, material_id):
        return cls.objects.filter(site_id=site_id, material_id=material_id).aggregate(
            b=Coalesce(Sum(cls.signed_qty()), Value(0), output_field=DecimalField(**QTY)))["b"]
