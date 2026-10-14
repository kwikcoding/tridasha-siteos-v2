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
            self.projects = self.make_projects(site, users)
            n = self.indents(site, users)
            m = self.modules(site, users)
        self.stdout.write(self.style.SUCCESS(f"Demo ready: {len(users)} logins (mobiles {MOBILE.format('01')}–{MOBILE.format('10')}), "
                                             f"{n} new demo indents on site DEMO; {m}."))
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

        n_ind = [0]

        def new(code, qty, purpose, by="engineer"):
            n_ind[0] += 1
            m = mats[code]
            data = {"site": site, "material": m, "item": m.name, "item_code": m.code, "unit": m.unit, "qty": qty,
                    "est_rate": m.std_rate, "priority": "normal", "purpose": f"[DEMO] {purpose}",
                    "project": self.projects["TA" if "Tower A" in purpose or n_ind[0] % 2 == 0 else "CH"],
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
                            ("accounts", "verifyInv", {"data": {"inv_no": "DEMO-INV-4", "inv_amount": 266000, "inv_gst": 47880}})]),
            ("DEMO-AAC", 600, "Terrace walls — payment waiting at 12b settle (Accountant)",
             po_steps(5) + [("store", "receive", {"qty": 600, "data": {"grn_no": "DEMO-GRN-5"}}), ("store", "issueClose"),
                            ("accounts", "verifyInv", {"data": {"inv_no": "DEMO-INV-5", "inv_amount": 228000, "inv_gst": 41040}}),
                            ("management", "authorizePay", {"data": {"pay_auth_amount": 269040}})]),
            ("DEMO-CEM", 50, "Repairs — fully issued from stock (closed)", to_rfq + [("store", "issue", {"qty": 50})]),
            ("DEMO-SAND", 25, "Wrong grade — sent back to the engineer", [("store", "sendback", {"remarks": "Please confirm zone and grade"})]),
        ]
        for code, qty, purpose, steps in plan:
            i = new(code, qty, purpose, by="supervisor" if "Repairs" in purpose else "engineer")
            walk(i, steps)
            made += 1
        return made

    def make_projects(self, site, U):
        from apps.sites.models import Project
        out = {}
        for code, name, budget, days in [("TA", "[Demo] Tower A — G+14 residential", 185000000, 540),
                                         ("CH", "[Demo] Clubhouse & amenities", 42000000, 300)]:
            p, _ = Project.objects.get_or_create(site=site, code=code, defaults=dict(
                name=name, status="active", budget=budget, head=U["pm"],
                start_date=timezone.localdate() - timedelta(days=120), end_date=timezone.localdate() + timedelta(days=days)))
            out[code] = p
        return out

    def modules(self, site, U):
        """Tasks, daily reports, labour, bills, quality & safety, documents and equipment — once per demo site."""
        from decimal import Decimal

        from django.contrib.contenttypes.models import ContentType
        from django.core.files.base import ContentFile

        from apps.compliance.models import Document, DocumentRevision, Observation
        from apps.core.models import Attachment
        from apps.finance.models import Expense, ExpensePayment
        from apps.plant.models import Allocation, Equipment, MaintenanceLog
        from apps.sitework.models import Attendance, DailyReport, Task, Worker
        if Task.objects.filter(site=site, title__startswith="[Demo]").exists():
            return "other modules already seeded"
        today = timezone.localdate()
        ta, ch = self.projects["TA"], self.projects["CH"]
        d = lambda n: today - timedelta(days=n)                      # noqa: E731

        # tasks (one overdue, one blocked, one waiting on another)
        t1 = Task.objects.create(site=site, project=ta, title="[Demo] L5 slab reinforcement check", assignee=U["engineer"],
                                 priority="high", status="in_progress", progress=60, start_date=d(3), due_date=d(1),
                                 created_by=U["pm"])
        Task.objects.create(site=site, project=ta, title="[Demo] L5 slab concrete pour", assignee=U["supervisor"],
                            priority="high", status="todo", start_date=today, due_date=today + timedelta(days=2),
                            depends_on=t1, created_by=U["pm"])
        Task.objects.create(site=site, project=ch, title="[Demo] Clubhouse footing excavation", assignee=U["supervisor"],
                            status="blocked", progress=30, due_date=today + timedelta(days=5), created_by=U["pm"])
        Task.objects.create(site=site, project=ta, title="[Demo] Shuttering material reconciliation", assignee=U["engineer"],
                            status="done", progress=100, due_date=d(4), completed_at=timezone.now() - timedelta(days=4),
                            created_by=U["pm"])
        Task.objects.create(site=site, title="[Demo] Monthly safety audit", assignee=U["safety"], priority="normal",
                            due_date=today + timedelta(days=10), created_by=U["pm"])

        # muster roll + attendance for the last 6 days (older days approved)
        crew = [("Ramesh K", "Mason", "Sai Labour Contractors", 950, 125), ("Suresh P", "Mason", "Sai Labour Contractors", 950, 125),
                ("Venkat R", "Bar bender", "Sai Labour Contractors", 900, 115), ("Lakshmi D", "Helper", "Sai Labour Contractors", 650, 85),
                ("Mahesh G", "Carpenter", "Sri Durga Works", 1000, 130), ("Anjali S", "Helper", "Sri Durga Works", 650, 85),
                ("Raju M", "Electrician", "", 1100, 140), ("Kiran T", "Helper", "", 650, 85)]
        workers = [Worker.objects.create(site=site, name=f"[Demo] {n}", worker_code=f"DW-{i + 1:02d}", trade=t, contractor=c,
                                         daily_wage=Decimal(w), ot_rate=Decimal(o), created_by=U["supervisor"])
                   for i, (n, t, c, w, o) in enumerate(crew)]
        pattern = ["present", "present", "present", "half", "present", "absent", "present", "present"]
        for day in range(1, 7):
            for i, w in enumerate(workers):
                st = pattern[(i + day) % len(pattern)]
                a = Attendance(worker=w, site=site, project=ta if i < 5 else ch, date=d(day), status=st,
                               ot_hours=Decimal("2") if st == "present" and i % 3 == 0 else Decimal("0"),
                               created_by=U["supervisor"], approved=day >= 3, approved_by=U["pm"] if day >= 3 else None)
                a.compute_wage()
                a.save()

        # daily progress reports: approved, approved, waiting approval, draft today
        for n, status in [(3, "approved"), (2, "approved"), (1, "submitted"), (0, "draft")]:
            DailyReport.objects.create(
                site=site, project=ta, date=d(n), weather="cloudy" if n % 2 else "clear", status=status,
                summary=f"[Demo] Tower A: L5 slab works day {4 - n} — rebar tying and shuttering",
                work_items=[{"activity": "Slab shuttering", "location": "Tower A L5", "qty": 180 + 20 * n, "unit": "sqm"},
                            {"activity": "Rebar tying", "location": "Tower A L5", "qty": 2.4 + n / 2, "unit": "MT"}],
                manpower=[{"trade": "Mason", "count": 12}, {"trade": "Bar bender", "count": 6}, {"trade": "Helper", "count": 18}],
                materials_used=[{"item": "Binding wire", "qty": 35, "unit": "kg"}],
                issues="Crane down for 2 hours" if n == 2 else "", tomorrow_plan="Continue L5 slab",
                created_by=U["engineer"], submitted_at=timezone.now() if status != "draft" else None,
                reviewed_by=U["pm"] if status == "approved" else None,
                reviewed_at=timezone.now() if status == "approved" else None)

        # bills at every stage
        def bill(payee, no, cat, amt, gst, status, **kw):
            e = Expense.objects.create(site=site, project=kw.pop("project", ta), date=d(kw.pop("ago", 5)), category=cat,
                                       description=kw.pop("desc", f"[Demo] {cat}"), payee=payee, bill_no=no,
                                       amount=Decimal(amt), gst=Decimal(gst), status=status, created_by=U["accounts"], **kw)
            if status in ("approved", "part_paid", "paid"):
                e.approved_amount, e.approved_by, e.approved_at = e.total, U["management"], timezone.now()
                e.save()
            return e
        bill("[Demo] Sai Labour Contractors", "SLC/24", "Labour contractor bill", 148000, 0, "draft", ago=1)
        bill("[Demo] Balaji Earthmovers", "BE-118", "Equipment hire", 60000, 10800, "submitted",
             desc="[Demo] JCB 3DX — 6 days", project=ch, submitted_at=timezone.now())
        bill("[Demo] Telangana Power", "TSPDCL-0925", "Utilities", 38500, 0, "approved")
        part = bill("[Demo] Sri Durga Works", "SDW-07", "Labour contractor bill", 92000, 0, "part_paid", ago=12)
        ExpensePayment.objects.create(expense=part, date=d(8), amount=Decimal("50000"), mode="NEFT", ref="DEMO-UTR-1", by=U["accounts"])
        part.paid_total = Decimal("50000")
        part.save()
        paid = bill("[Demo] HP Fuel Station", "HP-3321", "Fuel", 18400, 0, "paid", ago=15)
        ExpensePayment.objects.create(expense=paid, date=d(14), amount=paid.total, mode="UPI", ref="DEMO-UTR-2", by=U["accounts"])
        paid.paid_total = paid.total
        paid.save()
        bill("[Demo] Quick Movers", "QM-11", "Transport", 7500, 1350, "rejected", review_note="Duplicate of QM-10", ago=9)

        # quality & safety
        def obs(kind, ref, title, sev, status, **kw):
            return Observation.objects.create(site=site, project=kw.pop("project", ta), kind=kind, ref_no=ref, title=title,
                                              severity=sev, status=status, date=d(kw.pop("ago", 2)),
                                              created_by=kw.pop("by", U["safety"]), **kw)
        obs("safety", "DEMO-SO-001", "[Demo] Missing guard rail at L5 slab edge", "high", "open", assigned_to=U["supervisor"],
            due_date=d(-1), location="Tower A L5 east edge")
        ncr = obs("ncr", "DEMO-NCR-001", "[Demo] Honeycombing in column C4", "high", "in_progress", assigned_to=U["engineer"],
                  due_date=today + timedelta(days=3), corrective_action="Chip out loose concrete, grout with GP2", by=U["engineer"],
                  location="Tower A L4 grid C4")
        done = obs("inspection", "DEMO-QI-001", "[Demo] Pre-pour inspection L4 slab", "low", "closed", ago=8,
                   corrective_action="Cover blocks added", closure_note="Re-inspected and approved",
                   closed_by=U["safety"], closed_at=timezone.now() - timedelta(days=7), by=U["engineer"])
        obs("incident", "DEMO-INC-001", "[Demo] Minor hand injury — rebar cutting", "medium", "open", ago=1, project=ta,
            assigned_to=U["supervisor"], location="Rebar yard")
        obs("near_miss", "DEMO-NM-001", "[Demo] Shuttering plank fell from L5", "medium", "open", ago=3, project=ch)
        ct = ContentType.objects.get_for_model(Observation)
        for o, name in [(done, "pre-pour-checklist.pdf"), (ncr, "c4-before-repair.jpg")]:
            a = Attachment(content_type=ct, object_id=o.pk, name=name, size=24, uploaded_by=U["engineer"],
                           purpose="evidence" if o is done else "finding")
            a.file.save(name, ContentFile(b"%PDF-1.4 demo file" if name.endswith(".pdf") else b"\xff\xd8\xff demo"), save=False)
            a.size = a.file.size
            a.save()

        # drawings & documents with revisions
        for num, title, cat, revs in [("DEMO-TA-STR-101", "[Demo] Typical floor slab reinforcement", "drawing", ["R0", "R1"]),
                                      ("DEMO-TA-ARC-001", "[Demo] Tower A floor plan", "drawing", ["R0"]),
                                      ("DEMO-MS-005", "[Demo] Method statement — slab concreting", "method", ["R0"])]:
            doc = Document.objects.create(site=site, project=ta, category=cat, number=num, title=title,
                                          discipline="Structural" if "STR" in num else "Architectural", created_by=U["engineer"])
            for i, rev in enumerate(revs):
                r = DocumentRevision(document=doc, rev=rev, file_name=f"{num}-{rev}.pdf", note="First issue" if i == 0 else "Beam B4 deepened",
                                     status="Superseded" if i < len(revs) - 1 else "For construction", uploaded_by=U["engineer"])
                r.file.save(f"{num}-{rev}.pdf", ContentFile(f"%PDF-1.4 {num} {rev}\n".encode()), save=False)
                r.size = r.file.size
                r.save()

        # plant & equipment
        mixer = Equipment.objects.create(code="DEMO-MX-01", name="[Demo] Concrete mixer 10/7", category="Mixer", ownership="owned",
                                         status="in_use", site=site, project=ta, service_every_days=30,
                                         next_service_due=today + timedelta(days=12), created_by=U["store"])
        Allocation.objects.create(equipment=mixer, site=site, project=ta, from_date=d(20), by=U["store"])
        jcb = Equipment.objects.create(code="DEMO-JCB-01", name="[Demo] JCB 3DX backhoe", category="Excavator", ownership="hired",
                                       hire_rate=Decimal("6500"), supplier="[Demo] Balaji Earthmovers", status="breakdown",
                                       site=site, project=ch, created_by=U["store"])
        Allocation.objects.create(equipment=jcb, site=site, project=ch, from_date=d(9), by=U["store"])
        MaintenanceLog.objects.create(equipment=jcb, date=d(1), kind="breakdown", description="[Demo] Hydraulic hose burst",
                                      cost=Decimal("4800"), downtime_hours=Decimal("7"), by=U["store"])
        Equipment.objects.create(code="DEMO-DG-01", name="[Demo] 62.5 kVA DG set", category="DG set", ownership="owned",
                                 status="available", service_every_days=45, next_service_due=d(2), created_by=U["store"])
        Equipment.objects.create(code="DEMO-VIB-01", name="[Demo] Needle vibrator", category="Vibrator", ownership="owned",
                                 status="available", created_by=U["store"])
        return "tasks, daily reports, labour, bills, quality & safety, documents and equipment added"

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
