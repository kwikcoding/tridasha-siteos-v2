"""Performance at a realistic volume (about a year of one busy site): response time and number of database queries
for the main screens. Lists must not run one query per row (checked by comparing 10 vs 50 rows per page).
Timings are written to perf-results.json so CI can show them."""
import json
import os
import time
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.compliance.models import Document, Observation
from apps.finance.models import Expense
from apps.indents.models import Indent, IndentEvent
from apps.materials.models import Material, StockEntry
from apps.plant.models import Equipment
from apps.sites.models import Project, Site
from apps.sitework.models import Attendance, DailyReport, Task, Worker

PW = "Str0ng-pass-123"
TODAY = timezone.localdate()
LIMIT_S = float(os.environ.get("PERF_LIMIT_S", "2.0"))
RESULTS = []


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class Performance(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        site = cls.site = Site.objects.create(code="TIM", name="Tridasha Imperial")
        cls.admin = User.objects.create_superuser("9876543210", PW, name="Admin")
        cls.pm = User.objects.create_user("9100000001", PW, name="PM", role=Role.objects.get(key="pm"))
        cls.store = User.objects.create_user("9100000002", PW, name="Store", role=Role.objects.get(key="store"))
        cls.store.sites.add(site)
        u = cls.pm
        pa, pb = Project.objects.create(site=site, code="TA", name="Tower A"), Project.objects.create(site=site, code="TB", name="Tower B")
        stages = [("stock", "Requested"), ("tech", "Under Verification"), ("qs", "Under Verification"), ("mgmt", "Under Verification"), ("rfq", "Purchase Required"),
                  ("track", "PO Issued"), ("closed", "Closed")]
        inds = [Indent(number=f"IND-P-{n:05d}", site=site, project=pa if n % 2 else pb, item=f"Item {n % 40}", qty=10 + n % 7,
                       raised_by=u, stage=stages[n % 6][0], status=stages[n % 6][1], est_rate=100) for n in range(2000)]
        Indent.objects.bulk_create(inds, batch_size=500)
        IndentEvent.objects.bulk_create([IndentEvent(indent=i, action="raise", stage="raise", by=u, to_status=i.status)
                                         for i in Indent.objects.all()], batch_size=1000)
        mats = Material.objects.bulk_create([Material(code=f"M{n:04d}", name=f"Material {n}", unit="nos", reorder_level=5)
                                             for n in range(300)])
        StockEntry.objects.bulk_create([StockEntry(site=site, material=mats[n % 300], kind="IN" if n % 3 else "OUT",
                                                   qty=Decimal(5 if n % 3 else 1), date=TODAY - timedelta(days=n % 200), by=u)
                                        for n in range(3000)], batch_size=1000)
        workers = Worker.objects.bulk_create([Worker(site=site, name=f"Worker {n}", daily_wage=700, created_by=u) for n in range(50)])
        Attendance.objects.bulk_create([Attendance(worker=w, site=site, date=TODAY - timedelta(days=d), status="present",
                                                   wage=Decimal("700"), created_by=u)
                                        for w in workers for d in range(60)], batch_size=1000)
        DailyReport.objects.bulk_create([DailyReport(site=site, project=p, date=TODAY - timedelta(days=d), summary="Work",
                                                     work_items=[{"activity": "RCC", "qty": 10, "unit": "cum"}],
                                                     manpower=[{"trade": "Mason", "count": 10}], created_by=u, status="approved")
                                         for p in (pa, pb) for d in range(90)])
        Expense.objects.bulk_create([Expense(site=site, project=pa, date=TODAY - timedelta(days=n % 300), category="Fuel",
                                             description="d", payee=f"Payee {n % 30}", bill_no=f"B{n}", amount=Decimal("1000"),
                                             status=["draft", "submitted", "approved", "paid"][n % 4], created_by=u)
                                     for n in range(1500)], batch_size=500)
        Task.objects.bulk_create([Task(site=site, project=pa, title=f"Task {n}", due_date=TODAY - timedelta(days=n % 30 - 15),
                                       assignee=u, created_by=u) for n in range(1000)])
        Observation.objects.bulk_create([Observation(site=site, kind="safety", ref_no=f"SO-P-{n:04d}", title=f"Obs {n}",
                                                     created_by=u) for n in range(600)])
        Document.objects.bulk_create([Document(site=site, category="drawing", number=f"D-{n:04d}", title=f"Drawing {n}",
                                               created_by=u) for n in range(300)])
        Equipment.objects.bulk_create([Equipment(code=f"EQ-{n:03d}", name=f"Equipment {n}", created_by=u) for n in range(120)])

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        out = os.environ.get("PERF_OUT", "perf-results.json")
        with open(out, "w") as f:
            json.dump(sorted(RESULTS, key=lambda r: -r["ms"]), f, indent=1)

    def setUp(self):
        cache.clear()

    def measure(self, user, url, label):
        c = APIClient()
        c.force_authenticate(user)
        c.get(url)                                              # warm-up (first request loads code paths)
        with CaptureQueriesContext(connection) as q:
            t = time.perf_counter()
            r = c.get(url)
            ms = (time.perf_counter() - t) * 1000
        self.assertEqual(r.status_code, 200, (url, r.content[:200]))
        RESULTS.append({"screen": label, "url": url, "ms": round(ms, 1), "queries": len(q)})
        self.assertLess(ms / 1000, LIMIT_S, f"{label} took {ms:.0f} ms")
        return len(q)

    def test_main_screens_are_fast_at_volume(self):
        screens = [
            (self.pm, "/api/auth/pending/", "Dashboard counts (2,000 indents)"),
            (self.pm, "/api/indents/?tab=all", "Indents list"),
            (self.pm, "/api/indents/?tab=queue", "Indents — waiting for me"),
            (self.pm, f"/api/indents/{Indent.objects.first().pk}/", "Indent detail"),
            (self.pm, "/api/tasks/?open=1", "Tasks"), (self.pm, "/api/dpr/", "Daily reports"),
            (self.pm, "/api/dpr/summary/", "Project progress summary (180 reports)"),
            (self.pm, "/api/attendance/?page_size=200", "Attendance (3,000 marks)"),
            (self.pm, "/api/attendance/summary/", "Attendance summary & wages"),
            (self.pm, "/api/expenses/", "Bills (1,500)"), (self.pm, "/api/expenses/summary/", "Bills summary"),
            (self.pm, "/api/observations/", "Quality & safety (600)"), (self.pm, "/api/documents/", "Documents (300)"),
            (self.pm, "/api/equipment/", "Equipment (120)"), (self.pm, "/api/equipment/utilisation/", "Equipment utilisation"),
            (self.pm, "/api/materials/", "Catalogue (300)"),
            (self.store, f"/api/stock/balances/?site={self.site.pk}", "Stock balances (3,000 entries)"),
            (self.pm, "/api/reports/summary/", "Reports (all sections)"),
            (self.admin, "/api/audit/", "Audit log"),
        ]
        for user, url, label in screens:
            self.measure(user, url, label)

    def test_lists_do_not_query_once_per_row(self):
        for ep in ["indents/?tab=all&", "tasks/?", "dpr/?", "expenses/?", "observations/?", "documents/?", "equipment/?",
                   "attendance/?", "materials/?", "workers/?"]:
            small = self.measure(self.pm, f"/api/{ep}page_size=10", f"{ep} ×10")
            big = self.measure(self.pm, f"/api/{ep}page_size=50", f"{ep} ×50")
            self.assertLessEqual(big, small + 2, f"/api/{ep}: {small} queries for 10 rows but {big} for 50 (N+1)")
