"""Materials register, catalogue import, stock ledger, and indents moving stock."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.materials.models import Material, RegisterItem, StockEntry
from apps.materials.tests.test_importer import CATALOGUE_CSV, REGISTER_CSV
from apps.sites.models import Site

PW = "Str0ng-pass-123"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class MaterialsAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.site = Site.objects.create(code="TIM", name="Tridasha Imperial")

        def mk(mobile, name, role):
            u = User.objects.create_user(mobile, PW, name=name, role=Role.objects.get(key=role))
            u.sites.add(cls.site)
            return u

        cls.store = mk("9200000001", "Store", "store")
        cls.engineer = mk("9200000002", "Engineer", "engineer")
        cls.pm = mk("9200000003", "PM", "pm")
        cls.mgmt = mk("9200000004", "Mgmt", "management")
        cls.purchase = mk("9200000005", "Purchase", "purchase")
        cls.viewer = mk("9200000006", "Viewer", "viewer")
        cls.cement = Material.objects.create(code="CEM-53", name="OPC 53 Cement", unit="bag", std_rate=410)

    def c(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def upload(self, user, path, name, text, commit):
        f = SimpleUploadedFile(name, text.encode(), content_type="text/csv")
        return self.c(user).post(path, {"file": f, "commit": "true" if commit else "false"}, format="multipart")

    # ---------------------------------------------------------------- imports
    def test_catalogue_import_preview_then_commit(self):
        r = self.upload(self.store, "/api/materials/import/", "m.csv", CATALOGUE_CSV, commit=False)
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual((d["create"], d["update"], d["error_count"], d["committed"]), (1, 1, 1, False))
        self.assertEqual(Material.objects.count(), 1)          # preview changes nothing
        r = self.upload(self.store, "/api/materials/import/", "m.csv", CATALOGUE_CSV, commit=True)
        self.assertTrue(r.json()["committed"])
        self.assertEqual(Material.objects.count(), 2)
        self.cement.refresh_from_db()
        self.assertEqual(str(self.cement.std_rate), "410.50")
        # same file again: nothing to do
        d = self.upload(self.store, "/api/materials/import/", "m.csv", CATALOGUE_CSV, commit=True).json()
        self.assertEqual((d["create"], d["update"], d["unchanged"]), (0, 0, 2))

    def test_register_import_and_stats(self):
        d = self.upload(self.store, "/api/register/import/", "reg.csv", REGISTER_CSV, commit=True).json()
        self.assertEqual((d["create"], d["error_count"]), (2, 2))
        self.assertEqual(RegisterItem.objects.get(item_id="MAT-0001").status, "Ordered")
        s = self.c(self.store).get("/api/register/stats/").json()
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["applicability"]["Required"], 1)
        r = self.c(self.store).get("/api/register/export/")
        self.assertEqual(r.status_code, 200)

    def test_bad_file_message(self):
        r = self.upload(self.store, "/api/materials/import/", "x.pdf", "nope", commit=False)
        self.assertEqual(r.status_code, 400)
        self.assertIn("xlsx", r.json()["detail"])

    def test_viewer_cannot_import_or_post_stock(self):
        r = self.upload(self.viewer, "/api/materials/import/", "m.csv", CATALOGUE_CSV, commit=True)
        self.assertEqual(r.status_code, 403)
        r = self.c(self.viewer).post("/api/stock/", {"site": self.site.pk, "material": self.cement.pk, "kind": "IN",
                                                     "qty": 5}, format="json")
        self.assertEqual(r.status_code, 403)

    # ---------------------------------------------------------------- stock
    def test_stock_in_out_and_no_negative(self):
        c = self.c(self.store)
        r = c.post("/api/stock/", {"site": self.site.pk, "material": self.cement.pk, "kind": "IN", "qty": 100,
                                   "source": "opening"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = c.post("/api/stock/", {"site": self.site.pk, "material": self.cement.pk, "kind": "OUT", "qty": 150},
                   format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Only 100", r.json()["detail"])
        r = c.post("/api/stock/", {"site": self.site.pk, "material": self.cement.pk, "kind": "ADJ", "qty": -4},
                   format="json")
        self.assertEqual(r.status_code, 400)                    # adjustment needs a reason
        c.post("/api/stock/", {"site": self.site.pk, "material": self.cement.pk, "kind": "ADJ", "qty": -4,
                               "note": "Count on 13 Oct"}, format="json")
        bal = c.get(f"/api/stock/balances/?site={self.site.pk}").json()
        self.assertEqual(float(bal[0]["balance"]), 96.0)
        m = c.get(f"/api/materials/?site={self.site.pk}&search=CEM").json()["results"][0]
        self.assertEqual(float(m["balance"]), 96.0)
        self.assertEqual(c.get("/api/stock/export/").status_code, 200)

    # ---------------------------------------------------------------- indents move stock
    def test_linked_indent_moves_stock(self):
        StockEntry.objects.create(site=self.site, material=self.cement, kind="IN", qty=30, by=self.store,
                                  date="2026-10-01", source="opening")
        r = self.c(self.engineer).post("/api/indents/", {"site": self.site.pk, "material": self.cement.pk, "qty": 100},
                                       format="json")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual((d["item"], d["unit"], d["item_code"]), ("OPC 53 Cement", "bag", "CEM-53"))
        self.assertEqual(float(d["stock_at_site"]), 30.0)
        iid = d["id"]

        def act(u, action, **body):
            r = self.c(u).post(f"/api/indents/{iid}/act/", {"action": action, **body}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
            return r.json()

        act(self.store, "approve")
        act(self.pm, "approve")
        act(self.mgmt, "approve")
        # can't issue more than is in stock
        r = self.c(self.store).post(f"/api/indents/{iid}/act/", {"action": "issue", "qty": 40}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Only 30", r.json()["detail"])
        d = act(self.store, "issue", qty=30)
        self.assertEqual(float(d["stock_at_site"]), 0.0)
        act(self.purchase, "approve", data={"quotes": [{"vendor": "Ultratech", "rate": 400}]})
        act(self.mgmt, "approve", data={"vendor_final": "Ultratech", "rate": "400"})
        act(self.purchase, "po", data={"po_no": "PO-7", "po_vendor": "Ultratech", "po_rate": "400"})
        d = act(self.store, "receive", qty=70, data={"grn_no": "GRN-7"})
        self.assertEqual(float(d["stock_at_site"]), 70.0)
        d = act(self.store, "issueClose")
        self.assertEqual(float(d["stock_at_site"]), 0.0)
        kinds = [(e["kind"], float(e["qty"])) for e in d["stock_entries"]]
        self.assertEqual(kinds, [("OUT", 30.0), ("IN", 70.0), ("OUT", 70.0)])
        grn = StockEntry.objects.get(indent_id=iid, kind="IN")
        self.assertEqual((grn.ref, grn.party, str(grn.rate)), ("GRN-7", "Ultratech", "400.00"))

    def test_indent_without_material_still_works(self):
        r = self.c(self.engineer).post("/api/indents/", {"site": self.site.pk, "item": "Shuttering oil", "qty": 5},
                                       format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(r.json()["stock_at_site"])
        r = self.c(self.engineer).post("/api/indents/", {"site": self.site.pk, "qty": 5}, format="json")
        self.assertEqual(r.status_code, 400)
