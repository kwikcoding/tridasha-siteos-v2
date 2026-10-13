import io
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.indents.models import Indent
from apps.legacy.models import V1Record
from apps.materials.models import Material, RegisterItem, StockEntry
from apps.sites.models import Site

PW = "Str0ng-pass-123"

EXPORT = {"generatedAt": "2026-10-10T13:10:43Z", "tabs": [
    {"title": "Live – Sites", "sheet": "main", "header": ["Site", "Code", "Location", "Status"],
     "rows": [["Tridasha Imperial – Block A", "TI-A", "Kandi", "Active"], ["Tridasha Imperial – Block B", "TI-B", "", "Active"]]},
    {"title": "Live – Stock Balance", "sheet": "main",
     "header": ["Site", "Code", "Material", "Category", "Unit", "Received", "Issued", "Balance", "Re-order level (per site)", "Status", "Std rate ₹"],
     "rows": [["Tridasha Imperial – Block A", "A08", "OPC 53 cement", "Cement", "bag", 5000, 1200, 3800, 556, "OK", 390]]},
    {"title": "Live – Receipts & Issues", "sheet": "main",
     "header": ["Date", "Type", "Site", "Code", "Material", "Unit", "Qty", "Rate ₹", "Supplier / issued to", "DC / GRN / ref", "Entered by", "Entered at (IST)"],
     "rows": [["2026-10-10", "Issued to work", "Tridasha Imperial – Block A", "A08", "OPC 53 cement", "bag", 1200, 0, "", "", "Shyam", "2026-10-10 18:40"],
              ["2026-10-09", "Received", "Tridasha Imperial – Block A", "A08", "OPC 53 cement", "bag", 5000, 390, "Ultratech", "DC-1", "Shyam", "2026-10-10 18:40"]]},
    {"title": "Live – Receipts & Issues", "sheet": "materials", "header": ["Date"], "rows": [["2026-10-10"]]},
    {"title": "Live – Inventory", "sheet": "materials",
     "header": ["Code", "Group", "Material", "Unit", "Re-order level (per site)", "Rate ₹ (ex-GST)"],
     "rows": [["A01", "Concrete", "RMC M10", "cum", "", 4600], ["A08", "Concrete", "OPC 53 cement", "bag", 556, 390]]},
    {"title": "Live – Labour", "sheet": "main", "header": ["Date", "Site", "Contractor / gang", "Mason", "Helper"],
     "rows": [["2026-10-10", "Tridasha Imperial – Block A", "Ravi gang", 4, 6]]},
    {"title": "Live – Sync", "sheet": "main", "header": ["Item", "Value"], "rows": [["x", 1]]},
]}


def register_xlsx():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Materials Register"          # the hand-kept tab with title rows …
    ws.append(["HIGH-RISE MATERIALS REGISTER"])
    ws.append(["Item ID", "Trade", "Material / equipment item", "Applicability"])
    ws.append(["MAT-0001", "Civil", "OLD NAME", "To review"])
    live = wb.create_sheet("Live – Materials Register")   # … and the v1 one, which wins
    live.append(["Item ID", "Trade", "System / section", "Material / equipment item", "Unit", "Applicability",
                 "Procurement status", "SiteOS take-off code"])
    live.append(["MAT-0001", "Civil & Structure", "Concrete", "OPC cement", "t", "Required", "Ordered", "A08"])
    live.append(["MAT-0002", "Electrical", "Cables", "FRLS cable", "m", "To review", "Not started", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class V1Import(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.admin = User.objects.create_superuser("9876543210", PW, name="Admin")

    def upload(self, commit, *files):
        c = APIClient()
        c.force_authenticate(self.admin)
        return c.post("/api/legacy/import/", {"files": list(files), "commit": "true" if commit else "false"}, format="multipart")

    def files(self):
        return (SimpleUploadedFile("siteos-export.json", json.dumps(EXPORT).encode(), content_type="application/json"),
                SimpleUploadedFile("register.xlsx", register_xlsx(),
                                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))

    def test_preview_changes_nothing(self):
        r = self.upload(False, *self.files())
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertFalse(d["committed"])
        self.assertEqual(d["applied"]["Sites"]["created"], 2)
        self.assertEqual((Site.objects.count(), Material.objects.count(), V1Record.objects.count()), (0, 0, 0))

    def test_import_everything_and_rerun_is_safe(self):
        d = self.upload(True, *self.files()).json()
        self.assertTrue(d["committed"])
        a = Site.objects.get(code="TI-A")
        cem = Material.objects.get(code="A08")
        self.assertEqual((cem.category, str(cem.std_rate), str(cem.reorder_level)), ("Concrete", "390.00", "556.000"))
        self.assertEqual(StockEntry.objects.count(), 2)
        self.assertEqual(StockEntry.balance(a.pk, cem.pk), 3800)              # matches v1 Stock Balance
        self.assertEqual(d["stock_mismatches"], [])
        r1 = RegisterItem.objects.get(item_id="MAT-0001")
        self.assertEqual((r1.item, r1.status, r1.material_id), ("OPC cement", "Ordered", cem.pk))   # Live tab won
        self.assertEqual(RegisterItem.objects.count(), 2)
        self.assertEqual(V1Record.objects.filter(tab="Labour").count(), 1)
        self.assertEqual(V1Record.objects.filter(tab="Sync").count(), 0)
        self.assertIn("Labour", d["kept_for_later"])
        grn = StockEntry.objects.get(kind="IN")
        self.assertEqual((grn.party, grn.ref, grn.source), ("Ultratech", "DC-1", "purchase"))
        # second run: nothing doubled
        d2 = self.upload(True, *self.files()).json()
        self.assertEqual(StockEntry.objects.count(), 2)
        self.assertEqual(V1Record.objects.count(), d["archive"]["Labour"]["rows"] + sum(v["rows"] for k, v in d["archive"].items() if k != "Labour"))
        self.assertEqual(d2["applied"]["Sites"]["unchanged"], 2)

    def test_only_admin_can_import(self):
        u = User.objects.create_user("9100000001", PW, name="Store", role=Role.objects.get(key="store"))
        c = APIClient()
        c.force_authenticate(u)
        f = SimpleUploadedFile("x.json", json.dumps(EXPORT).encode())
        self.assertEqual(c.post("/api/legacy/import/", {"files": [f]}, format="multipart").status_code, 403)

    def test_bad_file(self):
        r = self.upload(False, SimpleUploadedFile("x.pdf", b"%PDF"))
        self.assertEqual(r.status_code, 400)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class DemoData(TestCase):
    def setUp(self):
        call_command("seed", verbosity=0)

    def test_demo_logins_and_queues(self):
        with self.captureOnCommitCallbacks(execute=True):
            call_command("seed_demo", password="Demo-pass-2026", stdout=io.StringIO())
        self.assertEqual(User.objects.filter(employee_id__startswith="DEMO-", is_active=True).count(), 10)
        store = User.objects.get(mobile="9000000003")
        self.assertTrue(store.check_password("Demo-pass-2026"))
        self.assertFalse(store.must_change_password)
        stages = set(Indent.objects.filter(purpose__startswith="[DEMO]").values_list("stage", flat=True))
        for st in ("stock", "tech", "mgmt", "avail", "rfq", "vendor", "po", "track", "issue", "requester", "closed"):
            self.assertIn(st, stages)
        pstages = set(Indent.objects.filter(purpose__startswith="[DEMO]").values_list("pstage", flat=True))
        for st in ("invoice", "payauth", "payment"):
            self.assertIn(st, pstages)
        c = APIClient()
        c.force_authenticate(store)
        self.assertGreaterEqual(c.get("/api/auth/pending/").json()["indents"], 3)
        # running again doesn't duplicate
        call_command("seed_demo", password="Demo-pass-2026", stdout=io.StringIO())
        self.assertEqual(Indent.objects.filter(purpose__startswith="[DEMO]").count(), 14)
        call_command("seed_demo", remove=True, stdout=io.StringIO())
        self.assertEqual(User.objects.filter(employee_id__startswith="DEMO-", is_active=True).count(), 0)

    def test_needs_password(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("seed_demo", password="short", stdout=io.StringIO())
