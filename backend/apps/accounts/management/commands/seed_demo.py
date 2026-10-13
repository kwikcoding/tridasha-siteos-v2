"""Demo logins for every role, plus indents waiting at every step — for trying the system out.

    DEMO_PASSWORD='choose-one' python manage.py seed_demo          # create / refresh
    python manage.py seed_demo --remove                            # switch demo logins off, cancel demo indents

Everything demo is clearly marked: site DEMO, logins named "Demo – …" with mobiles 90000000xx,
employee IDs DEMO-xx, materials DEMO-…, indents with purpose "[DEMO] …". Real data is not touched.
The password is never printed or stored in a file — you choose it with DEMO_PASSWORD.
"""
import os
from argparse import SUPPRESS as argparse_SUPPRESS
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Department, Role, User
from apps.indents import services
from apps.indents.models import Indent
from apps.materials.models import Material, StockEntry
from apps.sites.models import Site

DEMO_USERS = [  # mobile suffix, role, name, designation, department
    ("01", "engineer", "Demo – Site Engineer", "Site Engineer", "Projects"),
    ("02", "supervisor", "Demo – Site Supervisor", "Site Supervisor", "Projects"),
    ("03", "store", "Demo – Store Keeper", "Store Keeper", "Stores"),
    ("04", "pm", "Demo – Project Head", "Project Head", "Projects"),
    ("05", "management", "Demo – Management", "Director", "Management"),
    ("06", "purchase", "Demo – Purchase", "Purchase Officer", "Purchase"),
    ("07", "accounts", "Demo – Accountant", "Accountant", "Accounts"),
    ("08", "qs", "Demo – QS", "Quantity Surveyor", "Projects"),
    ("09", "safety", "Demo – Safety Officer", "Safety Officer", "Quality & Safety"),
    ("10", "viewer", "Demo – Viewer", "Auditor (read-only)", "Management"),
]
DEMO_MATERIALS = [
    ("DEMO-CEM", "[Demo] OPC 53 cement", "Cement", "bag", 390, 200, 600),
    ("DEMO-TMT12", "[Demo] TMT bar Fe550D 12 mm", "Steel", "kg", 68, 2000, 1500),
    ("DEMO-SAND", "[Demo] River sand", "Aggregates", "cum", 1800, 20, 5),
    ("DEMO-AAC", "[Demo] AAC block 600×200×150", "Masonry", "nos", 52, 1000, 0),
]
DEMO_SITE = ("DEMO", "Demo site (try-out data)")
MOBILE = "90000000{}"


class Command(BaseCommand):
    help = "Create demo logins for each role and indents waiting at every workflow step."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true", help="Switch demo logins off and cancel demo indents.")
        parser.add_argument("--password", default=None, help=argparse_SUPPRESS)

    def handle(self, *args, **opts):
        if opts["remove"]:
            return self.remove()
        password = opts.get("password") or os.environ.get("DEMO_PASSWORD", "")
        if len(password) < 8:
            raise CommandError("Set DEMO_PASSWORD (8+ characters) — it becomes the password of every demo login.")
        with transaction.atomic():
            site, _ = Site.objects.get_or_create(code=DEMO_SITE[0], defaults={"name": DEMO_SITE[1]})
            users = self.users(site, password)
            self.materials(site, users["store"])
            n = self.indents(site, users)
        self.stdout.write(self.style.SUCCESS(f"Demo ready: {len(users)} logins (mobiles {MOBILE.format('01')}–{MOBILE.format('10')}), "
                                             f"{n} new demo indents on site DEMO."))
        for suffix, key, name, *_ in DEMO_USERS:
            self.stdout.write(f"  {MOBILE.format(suffix)}  {name}")

    def users(self, site, password):
        out = {}
        for suffix, key, name, designation, dept in DEMO_USERS:
            d, _ = Department.objects.get_or_create(name=dept)
            role = Role.objects.get(key=key)
            u = User.objects.filter(mobile=MOBILE.format(suffix)).first()
            if u is None:
                u = User.objects.create_user(MOBILE.format(suffix), password, name=name, role=role)
            u.name, u.role, u.designation, u.department, u.is_active = name, role, designation, d, True
            u.employee_id = f"DEMO-{suffix}"
            u.must_change_password = False
            u.alert_whatsapp = u.alert_sms = u.alert_email = False      # demo logins never message anyone
            u.set_password(password)
            u.save()
            u.sites.add(site)
            u.__dict__.pop("_roles_cache", None)
            out[key] = u
        mgr = out["pm"]
        for k in ("engineer", "supervisor", "store", "qs", "safety"):
            out[k].reporting_manager = mgr
            out[k].save(update_fields=["reporting_manager"])
        return out

    def materials(self, site, store):
        for code, name, cat, unit, rate, reorder, opening in DEMO_MATERIALS:
            m, _ = Material.objects.update_or_create(code=code, defaults=dict(name=name, category=cat, unit=unit,
                                                                              std_rate=rate, reorder_level=reorder))
            if opening and not StockEntry.objects.filter(site=site, material=m, source="opening").exists():
                StockEntry.objects.create(site=site, material=m, kind="IN", qty=opening, source="opening",
                                          date=timezone.localdate() - timedelta(days=7), by=store, note="[DEMO] opening stock")

    def indents(self, site, U):
        if Indent.objects.filter(site=site, purpose__startswith="[DEMO]", status__in=["Requested", "Under Verification"]).count() >= 2:
            return 0          # already seeded — run --remove first for a fresh set
        mats = {m.code: m for m in Material.objects.filter(code__startswith="DEMO-")}

        def new(code, qty, purpose, by="engineer"):
            m = mats[code]
            data = {"site": site, "material": m, "item": m.name, "item_code": m.code, "unit": m.unit, "qty": qty,
                    "est_rate": m.std_rate, "priority": "normal", "purpose": f"[DEMO] {purpose}",
                    "need_by": timezone.localdate() + timedelta(days=10)}
            return services.raise_indent(U[by], data)

        def act(i, who, action, **kw):
            data = kw.pop("data", {})
            services.perform_action(i.pk, U[who], action, kw, data)
            return Indent.objects.get(pk=i.pk)

        to_rfq = [("store", "approve"), ("pm", "approve"), ("management", "approve")]
        quotes = {"quotes": [{"vendor": "Demo Traders", "rate": 380, "delivery_days": 3},
                             {"vendor": "Sample Suppliers", "rate": 395, "delivery_days": 2}]}

        def walk(i, steps):
            for who, a, *kw in steps:
                i = act(i, who, a, **(kw[0] if kw else {}))
            return i

        through_po = to_rfq + [("store", "purchase", {}), ("purchase", "approve", {"data": quotes}),
                               ("management", "approve", {"data": {"vendor_final": "Demo Traders", "rate": 380}}),
                               ("purchase", "po", {"data": {"po_no": "DEMO-PO-{n}", "po_vendor": "Demo Traders", "po_rate": 380,
                                                            "po_expected": str(timezone.localdate() + timedelta(days=3))}})]

        def po_steps(n):
            out = []
            for s in through_po:
                if s[1] == "po":
                    d = dict(s[2]["data"])
                    d["po_no"] = d["po_no"].format(n=n)
                    out.append(("purchase", "po", {"data": d}))
                else:
                    out.append(s)
            return out

        made = 0
        plan = [
            ("DEMO-CEM", 100, "Tower A slab — waiting at 02 stock check (Store Keeper)", []),
            ("DEMO-TMT12", 3000, "Tower A columns — waiting at 03 technical (Project Head)", [("store", "approve")]),
            ("DEMO-SAND", 40, "Plastering — waiting at 04 budget approval (Management)", [("store", "approve"), ("pm", "approve")]),
            ("DEMO-CEM", 800, "Block work — waiting at stock decision (Store Keeper)", to_rfq),
            ("DEMO-AAC", 5000, "Partition walls — waiting at 05 quotations (Purchase)", to_rfq + [("store", "purchase")]),
            ("DEMO-AAC", 2000, "Lift core — waiting at 06 supplier approval (Management)",
             to_rfq + [("store", "purchase"), ("purchase", "approve", {"data": quotes})]),
            ("DEMO-SAND", 30, "Screed — waiting at 07 purchase order (Purchase)",
             to_rfq + [("store", "purchase"), ("purchase", "approve", {"data": quotes}),
                       ("management", "approve", {"data": {"vendor_final": "Demo Traders", "rate": 1750}})]),
            ("DEMO-AAC", 1500, "Parapet — on order, waiting for delivery (Store / Engineer receive)", po_steps(1)),
            ("DEMO-AAC", 1200, "Toilet walls — received, waiting at 10 issue & close", po_steps(2) + [("store", "receive", {"qty": 1200, "data": {"grn_no": "DEMO-GRN-2"}})]),
            ("DEMO-AAC", 900, "Shaft walls — invoice waiting at 11 (Accountant)",
             po_steps(3) + [("store", "receive", {"qty": 900, "data": {"grn_no": "DEMO-GRN-3"}}), ("store", "issueClose")]),
            ("DEMO-AAC", 700, "Staircase walls — payment waiting at 12a authorise (Management)",
             po_steps(4) + [("store", "receive", {"qty": 700, "data": {"grn_no": "DEMO-GRN-4"}}), ("store", "issueClose"),
                            ("accounts", "verifyInv", {"data": {"inv_no": "DEMO-INV-4", "inv_amount": 36400}})]),
            ("DEMO-AAC", 600, "Terrace walls — payment waiting at 12b settle (Accountant)",
             po_steps(5) + [("store", "receive", {"qty": 600, "data": {"grn_no": "DEMO-GRN-5"}}), ("store", "issueClose"),
                            ("accounts", "verifyInv", {"data": {"inv_no": "DEMO-INV-5", "inv_amount": 31200}}),
                            ("management", "authorizePay")]),
            ("DEMO-CEM", 50, "Repairs — fully issued from stock (closed)", to_rfq + [("store", "issue", {"qty": 50})]),
            ("DEMO-SAND", 25, "Wrong grade — sent back to the engineer", [("store", "sendback", {"remarks": "Please confirm zone and grade"})]),
        ]
        for code, qty, purpose, steps in plan:
            i = new(code, qty, purpose, by="supervisor" if "Repairs" in purpose else "engineer")
            walk(i, steps)
            made += 1
        return made

    def remove(self):
        with transaction.atomic():
            n_users = User.objects.filter(mobile__startswith="90000000", employee_id__startswith="DEMO-").update(is_active=False)
            n_ind = 0
            for i in Indent.objects.filter(purpose__startswith="[DEMO]").exclude(status__in=["Closed", "Stock Issued", "Rejected", "Cancelled"]):
                i.status, i.stage, i.close_reason = "Cancelled", "closed", "Demo data removed"
                i.closed_at = timezone.now()
                i.save(update_fields=["status", "stage", "close_reason", "closed_at"])
                n_ind += 1
            Site.objects.filter(code=DEMO_SITE[0]).update(active=False)
        self.stdout.write(self.style.SUCCESS(f"Demo logins switched off: {n_users}. Demo indents cancelled: {n_ind}. "
                                             f"Site DEMO hidden. (History is kept; nothing is deleted.)"))
