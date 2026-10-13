"""Import SiteOS v1 data into v2.

    run(files, user, commit=False)  → preview: everything is applied inside a transaction and rolled back
    run(files, user, commit=True)   → applied

Re-running is safe: sites, materials and register rows are matched by code / item ID, stock rows and archive rows
by a key built from the row itself, so nothing is doubled.
"""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from apps.materials import importer
from apps.materials.models import Material, RegisterItem, StockEntry
from apps.materials.services import REGISTER_FIELDS, _same
from apps.sites.models import Site

from . import v1parse as p
from .models import V1Record

STOCK_KIND = {"received": ("IN", "purchase"), "in": ("IN", "purchase"), "issued to work": ("OUT", "indent-issue"),
              "issued": ("OUT", "indent-issue"), "out": ("OUT", "indent-issue"), "returned": ("IN", "site-return"),
              "ret": ("IN", "site-return"), "adjustment": ("ADJ", "adjust"), "adj": ("ADJ", "adjust")}


class _Rollback(Exception):
    pass


def _num(v):
    try:
        return importer.to_number(v)
    except ValueError:
        return None


def _date(v):
    try:
        return importer.to_date(v)
    except ValueError:
        return None


def _site_code(name: str) -> str:
    words = [w for w in importer.norm(name).upper().split() if w]
    return ("-".join(w[:3] for w in words[:3]) or "SITE")[:20]


class Importer:
    def __init__(self, tabs, user):
        self.tabs = tabs
        self.user = user
        self.report = {}
        self.sites_by_key = {}

    def stat(self, tab):
        return self.report.setdefault(tab, {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "errors": []})

    def err(self, tab, line, msg):
        st = self.stat(tab)
        st["skipped"] += 1
        if len(st["errors"]) < 50:
            st["errors"].append({"line": line, "message": msg})

    def upsert(self, tab, model, lookup: dict, values: dict):
        obj = model.objects.filter(**lookup).first()
        values = {k: v for k, v in values.items() if v not in (None, "")}
        st = self.stat(tab)
        if obj is None:
            obj = model.objects.create(**lookup, **values)
            st["created"] += 1
            return obj
        changed = [k for k, v in values.items() if not _same(getattr(obj, k), v)]
        if changed:
            for k in changed:
                setattr(obj, k, values[k])
            obj.save(update_fields=changed)
            st["updated"] += 1
        else:
            st["unchanged"] += 1
        return obj

    # ---------------------------------------------------------------- sites
    def sites(self):
        for ix, r in enumerate(self.tabs.get("Sites", {}).get("rows", []), start=2):
            name = str(p.g(r, "Site", "Name", default="")).strip()
            if not name:
                self.err("Sites", ix, "No site name")
                continue
            code = str(p.g(r, "Code", default="") or _site_code(name)).strip().upper()[:20]
            status = str(p.g(r, "Status", default="Active"))
            s = self.upsert("Sites", Site, {"code": code}, {"name": name[:120], "address": str(p.g(r, "Location", default=""))[:255],
                                                              "active": status.lower() not in ("closed", "completed", "inactive")})
            self.sites_by_key[importer.norm(name)] = s
            self.sites_by_key[importer.norm(code)] = s

    def site_for(self, name):
        key = importer.norm(name)
        if key in self.sites_by_key:
            return self.sites_by_key[key]
        s = Site.objects.filter(name__iexact=str(name).strip()).first() or Site.objects.filter(code__iexact=str(name).strip()).first()
        if s is None and name:
            s = Site.objects.create(code=_site_code(name), name=str(name)[:120])
            self.stat("Sites")["created"] += 1
        if s:
            self.sites_by_key[key] = s
        return s

    # ---------------------------------------------------------------- materials
    def materials(self):
        inv = self.tabs.get("Inventory", {}).get("rows", [])
        bal = self.tabs.get("Stock Balance", {}).get("rows", [])
        for ix, r in enumerate(inv, start=2):
            code = importer.to_code(p.g(r, "Code"))
            name = p.g(r, "Material", "Name")
            if not code or not name:
                self.err("Inventory", ix, "Code or material name is empty")
                continue
            self.upsert("Inventory", Material, {"code": code}, {
                "name": str(name)[:255], "category": str(p.g(r, "Group", "Category", default=""))[:100],
                "unit": str(p.g(r, "Unit", default=""))[:20], "std_rate": _num(p.g(r, "Rate ₹ (ex-GST)", "Rate", "Std rate ₹")),
                "reorder_level": _num(p.g(r, "Re-order level (per site)", "Reorder level")),
            })
        known = set(Material.objects.values_list("code", flat=True))
        for ix, r in enumerate(bal, start=2):            # items only in the stock tab
            code = importer.to_code(p.g(r, "Code"))
            if not code or (code in known and inv):
                continue
            self.upsert("Stock Balance", Material, {"code": code}, {
                "name": str(p.g(r, "Material", default=code))[:255], "category": str(p.g(r, "Category", default=""))[:100],
                "unit": str(p.g(r, "Unit", default=""))[:20], "std_rate": _num(p.g(r, "Std rate ₹")),
                "reorder_level": _num(p.g(r, "Re-order level (per site)"))})
            known.add(code)

    def material_for(self, code, name, unit):
        code = importer.to_code(code)
        m = Material.objects.filter(code=code).first() if code else None
        if m is None and name:
            m = Material.objects.filter(name__iexact=str(name).strip()).first()
        if m is None and (code or name):
            m = Material.objects.create(code=code or importer.to_code(str(name))[:80], name=str(name or code)[:255],
                                        unit=str(unit or "")[:20])
            self.stat("Inventory")["created"] += 1
        return m

    # ---------------------------------------------------------------- stock ledger
    def stock(self):
        tab = "Receipts & Issues"
        rows = self.tabs.get(tab, {}).get("rows", [])
        keys = p.row_keys(rows)
        existing = set(StockEntry.objects.filter(import_key__in=[f"v1:{k}" for k in keys]).values_list("import_key", flat=True))
        new = []
        for ix, (r, k) in enumerate(zip(rows, keys), start=2):
            ik = f"v1:{k}"
            if ik in existing:
                self.stat(tab)["unchanged"] += 1
                continue
            kind_src = STOCK_KIND.get(importer.norm(p.g(r, "Type", default="")))
            d = _date(p.g(r, "Date"))
            qty = _num(p.g(r, "Qty", "Quantity"))
            site = self.site_for(p.g(r, "Site", default=""))
            mat = self.material_for(p.g(r, "Code"), p.g(r, "Material"), p.g(r, "Unit"))
            if not kind_src:
                self.err(tab, ix, f"Unknown type “{p.g(r, 'Type', default='')}”")
                continue
            if not (d and qty is not None and site and mat):
                self.err(tab, ix, "Date, quantity, site or material missing")
                continue
            kind, source = kind_src
            if kind in ("IN", "OUT"):
                qty = abs(qty)
            if qty == 0:
                self.err(tab, ix, "Quantity is zero")
                continue
            note = "; ".join(x for x in [
                f"Used at: {p.g(r, 'Used at')}" if p.g(r, "Used at") else "",
                f"Vehicle: {p.g(r, 'Vehicle')}" if p.g(r, "Vehicle") else "",
                str(p.g(r, "Notes", default="")),
                f"v1 entry by {p.g(r, 'Entered by')}" + (f" at {p.g(r, 'Entered at (IST)')}" if p.g(r, "Entered at (IST)") else "")
                if p.g(r, "Entered by") else "v1 entry"] if x)
            new.append(StockEntry(site=site, material=mat, date=d, kind=kind, qty=qty, source=source,
                                  rate=_num(p.g(r, "Rate ₹", "Rate")) or None, ref=str(p.g(r, "DC / GRN / ref", "Ref", default=""))[:80],
                                  party=str(p.g(r, "Supplier / issued to", default=""))[:150], note=note, by=self.user,
                                  import_key=ik))
        StockEntry.objects.bulk_create(new, batch_size=500)
        self.stat(tab)["created"] += len(new)

    def check_balances(self):
        """Compare v2 balances with v1's own 'Stock Balance' tab."""
        out = []
        for r in self.tabs.get("Stock Balance", {}).get("rows", []):
            site = self.site_for(p.g(r, "Site", default=""))
            code = importer.to_code(p.g(r, "Code"))
            m = Material.objects.filter(code=code).first()
            want = _num(p.g(r, "Balance"))
            if not (site and m) or want is None:
                continue
            have = StockEntry.balance(site.pk, m.pk)
            if abs(Decimal(have) - want) > Decimal("0.01"):
                out.append({"site": site.name, "code": code, "v1": str(want), "v2": str(have)})
        return out

    # ---------------------------------------------------------------- register
    def register(self):
        t = self.tabs.get("Materials Register")
        if not t:
            return
        spec = dict(importer.REGISTER)
        spec["material_code"] = ("code", ["siteos take off code", "catalogue code", "take off code"])
        raw = t.get("raw")
        if raw is None:      # from JSON: rebuild a table
            header = list(t["rows"][0].keys()) if t["rows"] else []
            raw = [header] + [[r.get(h) for h in header] for r in t["rows"]]
        try:
            parsed = importer.parse(raw, spec, importer.REGISTER_KEY, importer.REGISTER_REQUIRED)
        except importer.ImportError_ as e:
            self.err("Materials Register", 0, str(e))
            return
        for e in parsed["errors"]:
            self.err("Materials Register", e["line"], e["message"])
        mats = {m.code: m for m in Material.objects.all()}
        for row in parsed["rows"]:
            d = row["data"]
            vals = {f: d[f] for f in REGISTER_FIELDS if f in d}
            if d.get("material_code") and d["material_code"] in mats:
                vals["material"] = mats[d["material_code"]]
            self.upsert("Materials Register", RegisterItem, {"item_id": d["item_id"]}, vals)

    # ---------------------------------------------------------------- archive: every row of every tab
    def archive(self):
        for tab, t in self.tabs.items():
            rows = t.get("rows", [])
            keys = p.row_keys(rows)
            have = set(V1Record.objects.filter(tab=tab, key__in=keys).values_list("key", flat=True))
            new = [V1Record(tab=tab, key=k, row_no=n, data={h: (str(v) if v is not None and not isinstance(v, (int, float, str, bool)) else v)
                                                             for h, v in r.items()}, source_file=t.get("file", "")[:200])
                   for n, (r, k) in enumerate(zip(rows, keys), start=1) if k not in have]
            V1Record.objects.bulk_create(new, batch_size=500)
            self.report.setdefault("archive", {})[tab] = {"rows": len(rows), "new": len(new)}

    def run(self):
        self.sites()
        self.materials()
        self.stock()
        self.register()
        self.archive()
        mismatches = self.check_balances()
        return mismatches


NOT_YET = {"Indents": "old v1 indents", "Bills": "Expenses & bills", "Labour": "Labour & attendance",
           "Daily Reports": "Daily progress", "Tasks": "Tasks & schedule", "Quality & Safety": "Quality & safety",
           "Equipment": "Plant & equipment", "Take-off Detail": "Take-off"}


def run(files: list[tuple[str, bytes]], user, commit: bool) -> dict:
    tabs = p.merge(files)
    if not tabs:
        raise importer.ImportError_("No SiteOS v1 tabs found in these files.")
    imp = Importer(tabs, user)
    result = {}
    try:
        with transaction.atomic():
            mismatches = imp.run()
            result = {"committed": commit, "tabs": {t: {"rows": len(v["rows"]), "file": v["file"], "live": v["live"]}
                                                    for t, v in tabs.items()},
                      "applied": {k: v for k, v in imp.report.items() if k != "archive"},
                      "archive": imp.report.get("archive", {}), "stock_mismatches": mismatches,
                      "kept_for_later": {t: NOT_YET[t] for t in tabs if t in NOT_YET and tabs[t]["rows"]}}
            if not commit:
                raise _Rollback()
    except _Rollback:
        pass
    return result
