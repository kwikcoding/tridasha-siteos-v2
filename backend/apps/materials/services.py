"""Stock postings and upload imports — the only writers of the ledger and bulk data."""
from datetime import date as date_cls
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from . import importer
from .models import Material, RegisterItem, StockEntry


class StockError(Exception):
    """User-facing stock problem (e.g. not enough stock)."""


def _fmt(q: Decimal) -> str:
    return f"{q.normalize():f}" if q == q.to_integral() else f"{q:f}".rstrip("0")


@transaction.atomic
def post_entry(*, site, material, kind, qty, by, source="manual", date=None, rate=None, indent=None, ref="",
               party="", note="") -> StockEntry:
    qty = Decimal(str(qty))
    if kind not in (StockEntry.IN, StockEntry.OUT, StockEntry.ADJ):
        raise StockError("Unknown entry type.")
    if kind in (StockEntry.IN, StockEntry.OUT) and qty <= 0:
        raise StockError("Quantity must be more than zero.")
    if kind == StockEntry.ADJ and (qty == 0 or not note.strip()):
        raise StockError("An adjustment needs a non-zero quantity (use − to reduce) and a reason.")
    # serialise postings per material so two issues can't both take the last bags
    Material.objects.select_for_update().filter(pk=material.pk).first()
    if kind == StockEntry.OUT or (kind == StockEntry.ADJ and qty < 0):
        have = StockEntry.balance(site.pk, material.pk)
        take = qty if kind == StockEntry.OUT else -qty
        if take > have:
            raise StockError(f"Only {_fmt(have)} {material.unit or ''} of {material.name} in stock at {site.name}.".replace("  ", " "))
    return StockEntry.objects.create(site=site, material=material, kind=kind, qty=qty, by=by, source=source,
                                     date=date or timezone.localdate(), rate=rate, indent=indent, ref=ref[:80],
                                     party=party[:150], note=note)


# ---------------------------------------------------------------- imports
CATALOGUE_FIELDS = ["name", "category", "unit", "spec", "hsn", "gst_rate", "std_rate", "reorder_level"]
REGISTER_FIELDS = ["trade", "system", "item", "unit", "spec", "applicability", "zone", "req_qty", "grade", "make",
                   "vendor", "boq_ref", "status", "required_by", "remarks"]


def _same(a, b):
    if isinstance(a, Decimal) or isinstance(b, Decimal):
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except Exception:
            return False
    if isinstance(a, date_cls) or isinstance(b, date_cls):
        return a == b
    return (a or "") == (b or "")


def run_import(kind: str, filename: str, content: bytes, commit: bool) -> dict:
    """Preview (commit=False) or apply an upload. Upsert by code / item id; blank cells never wipe data."""
    if kind == "catalogue":
        parsed, model, key, fields = importer.parse_catalogue(filename, content), Material, "code", CATALOGUE_FIELDS
    elif kind == "register":
        parsed, model, key, fields = importer.parse_register(filename, content), RegisterItem, "item_id", REGISTER_FIELDS
    else:
        raise importer.ImportError_("Unknown import type.")

    keys = [r["data"][key] for r in parsed["rows"]]
    existing = {getattr(o, key): o for o in model.objects.filter(**{f"{key}__in": keys})}
    create, update, unchanged = [], [], 0
    for r in parsed["rows"]:
        d = r["data"]
        obj = existing.get(d[key])
        vals = {f: d[f] for f in fields if f in d and d[f] not in ("", None)}
        if obj is None:
            create.append(model(**{key: d[key]}, **vals))
        else:
            changed = [f for f, v in vals.items() if not _same(getattr(obj, f), v)]
            if changed:
                for f in changed:
                    setattr(obj, f, vals[f])
                update.append((obj, changed))
            else:
                unchanged += 1

    result = {
        "kind": kind, "columns": parsed["columns"], "errors": parsed["errors"][:200], "error_count": len(parsed["errors"]),
        "create": len(create), "update": len(update), "unchanged": unchanged, "committed": False,
        "sample_new": [getattr(o, key) for o in create[:10]],
        "sample_changed": [{"key": getattr(o, key), "fields": ch} for o, ch in update[:10]],
    }
    if commit:
        with transaction.atomic():
            model.objects.bulk_create(create, batch_size=500)
            all_fields = sorted({f for _, ch in update for f in ch})
            if update:
                model.objects.bulk_update([o for o, _ in update], all_fields, batch_size=500)
        result["committed"] = True
    return result


def low_stock_count(user) -> int:
    """Catalogue items at or below their reorder level, on the sites this person can see."""
    from django.db.models import Sum

    from apps.sites.models import Site
    sites = Site.objects.filter(active=True)
    if not user.all_sites:
        sites = sites.filter(pk__in=user.site_ids())
    levels = dict(Material.objects.filter(active=True, reorder_level__isnull=False).values_list("id", "reorder_level"))
    if not levels:
        return 0
    rows = (StockEntry.objects.filter(site__in=sites, material_id__in=levels).values("site", "material")
            .annotate(b=Sum(StockEntry.signed_qty())))
    return sum(1 for r in rows if r["b"] <= levels[r["material"]])
