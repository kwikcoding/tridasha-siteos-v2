"""API tests — separate logins per role walk one indent through all 12 steps."""
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.alerts.models import Notification
from apps.indents.models import Indent
from apps.sites.models import Site

PW = "Str0ng-pass-123"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class IndentFlowAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.site = Site.objects.create(code="TIM", name="Tridasha Imperial")
        cls.other_site = Site.objects.create(code="OTH", name="Other site")

        def mk(mobile, name, role):
            u = User.objects.create_user(mobile, PW, name=name, role=Role.objects.get(key=role))
            u.sites.add(cls.site)
            return u

        cls.admin = User.objects.create_superuser("9876543210", PW, name="Admin")
        cls.engineer = mk("9100000001", "Engineer", "engineer")
        cls.store = mk("9100000002", "Store", "store")
        cls.pm = mk("9100000003", "Project Head", "pm")
        cls.mgmt = mk("9100000004", "Management", "management")
        cls.purchase = mk("9100000005", "Purchase", "purchase")
        cls.accounts = mk("9100000006", "Accounts", "accounts")

    def setUp(self):
        cache.clear()   # login throttle

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_login_with_mobile_and_password(self):
        c = APIClient()
        r = c.post("/api/auth/login/", {"mobile": "+91 91000 00001", "password": PW}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["role"]["key"], "engineer")
        self.assertEqual(c.get("/api/auth/me/").json()["name"], "Engineer")

    def act(self, user, indent_id, action, expect=200, **body):
        r = self.client_for(user).post(f"/api/indents/{indent_id}/act/", {"action": action, **body}, format="json")
        self.assertEqual(r.status_code, expect, r.content)
        return r.json()

    def raise_indent(self, qty=100):
        r = self.client_for(self.engineer).post("/api/indents/", {
            "site": self.site.pk, "item": "OPC 53 Cement", "unit": "bag", "qty": qty, "est_rate": 400,
            "purpose": "Slab casting, Tower A"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    # ---------------------------------------------------------------- tests
    def test_login_wrong_password(self):
        r = APIClient().post("/api/auth/login/", {"mobile": self.engineer.mobile, "password": "nope"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_me_requires_login(self):
        self.assertEqual(APIClient().get("/api/auth/me/").status_code, 403)

    def test_full_12_step_flow(self):
        d = self.raise_indent()
        iid = d["id"]
        self.assertEqual((d["stage"], d["status"]), ("stock", "Requested"))
        self.assertTrue(d["number"].startswith("IND-"))

        d = self.act(self.store, iid, "approve", remarks="Stock 30 bags")
        self.assertEqual(d["stage"], "tech")
        d = self.act(self.pm, iid, "approve", qty_to=80)
        self.assertEqual((d["stage"], float(d["approved_qty"])), ("mgmt", 80.0))
        d = self.act(self.mgmt, iid, "approve")
        self.assertEqual(d["stage"], "avail")
        d = self.act(self.store, iid, "issue", qty=30)
        self.assertEqual((d["stage"], float(d["purchase_qty"])), ("rfq", 50.0))
        d = self.act(self.purchase, iid, "approve", data={"quotes": [{"vendor": "Ultratech", "rate": 390},
                                                                     {"vendor": "ACC", "rate": 395}]})
        self.assertEqual(d["stage"], "vendor")
        d = self.act(self.mgmt, iid, "approve", data={"vendor_final": "Ultratech", "rate": "390"})
        self.assertEqual(d["stage"], "po")
        d = self.act(self.purchase, iid, "po", data={"po_no": "PO-101", "po_vendor": "Ultratech", "po_rate": "390",
                                                     "po_expected": "2026-10-20"})
        self.assertEqual((d["stage"], d["status"]), ("track", "PO Issued"))
        d = self.act(self.engineer, iid, "receive", qty=50, data={"grn_no": "GRN-1", "inspection": "OK"})
        self.assertEqual((d["stage"], d["pstage"]), ("issue", "invoice"))
        d = self.act(self.store, iid, "issueClose", data={"issued_to": "Tower A gang"})
        self.assertEqual((d["stage"], d["status"]), ("closed", "Closed"))
        d = self.act(self.accounts, iid, "verifyInv", data={"inv_no": "INV-9", "inv_amount": "19500"})
        self.assertEqual(d["pstage"], "payauth")
        d = self.act(self.mgmt, iid, "authorizePay", data={"pay_auth_amount": "19500"})
        self.assertEqual((d["pstage"], d["pstatus"]), ("payment", "Payment Authorised"))
        d = self.act(self.accounts, iid, "pay", data={"paid_on": "2026-10-25", "pay_mode": "NEFT", "pay_amount": "19500"})
        self.assertEqual((d["pstage"], d["pstatus"]), ("closed", "Purchase Closed"))

        self.assertTrue(all(st["state"] == "done" for st in d["steps"]), d["steps"])
        actions = [h["action"] for h in d["history"]]
        self.assertEqual(actions, ["raise", "approve", "approve", "approve", "issue", "approve", "approve", "po",
                                   "receive", "issueClose", "verifyInv", "authorizePay", "pay"])
        self.assertEqual(d["history"][8]["grn_no"], "GRN-1")

    def test_wrong_role_is_refused(self):
        d = self.raise_indent()
        r = self.act(self.pm, d["id"], "approve", expect=400)
        self.assertIn("can’t", r["detail"])

    def test_cannot_set_fields_of_another_step(self):
        d = self.raise_indent()
        r = self.act(self.store, d["id"], "approve", expect=400, data={"po_no": "HACK"})
        self.assertIn("po_no", r["detail"])

    def test_status_cannot_be_patched(self):
        d = self.raise_indent()
        c = self.client_for(self.engineer)
        c.patch(f"/api/indents/{d['id']}/", {"status": "Closed", "qty": 5}, format="json")
        i = Indent.objects.get(pk=d["id"])
        self.assertEqual((i.status, float(i.qty)), ("Requested", 5.0))   # qty editable, status ignored

    def test_requester_cannot_edit_after_approval(self):
        d = self.raise_indent()
        self.act(self.store, d["id"], "approve")
        r = self.client_for(self.engineer).patch(f"/api/indents/{d['id']}/", {"qty": 5}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_queue_tab(self):
        d = self.raise_indent()
        ids = [x["id"] for x in self.client_for(self.store).get("/api/indents/?tab=queue").json()["results"]]
        self.assertIn(d["id"], ids)
        ids = [x["id"] for x in self.client_for(self.pm).get("/api/indents/?tab=queue").json()["results"]]
        self.assertNotIn(d["id"], ids)

    def test_site_isolation(self):
        outsider = User.objects.create_user("9100000099", PW, name="Other engineer",
                                            role=Role.objects.get(key="engineer"))
        outsider.sites.add(self.other_site)
        d = self.raise_indent()
        c = self.client_for(outsider)
        self.assertEqual(c.get(f"/api/indents/{d['id']}/").status_code, 404)
        r = c.post("/api/indents/", {"site": self.site.pk, "item": "Sand", "qty": 1}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_sendback_needs_remark_and_resubmit(self):
        d = self.raise_indent()
        self.act(self.store, d["id"], "sendback", expect=400)
        d = self.act(self.store, d["id"], "sendback", remarks="Wrong grade")
        self.assertEqual(d["stage"], "requester")
        d = self.act(self.engineer, d["id"], "resubmit", data={"item": "OPC 43 Cement"})
        self.assertEqual((d["stage"], d["item"]), ("stock", "OPC 43 Cement"))

    def test_alerts_created_for_next_step(self):
        with self.captureOnCommitCallbacks(execute=True):
            d = self.raise_indent()
        self.assertTrue(Notification.objects.filter(user=self.store, indent_id=d["id"], kind="waiting").exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.act(self.store, d["id"], "sendback", remarks="Wrong grade")
        self.assertTrue(Notification.objects.filter(user=self.engineer, kind="returned").exists())

    def test_only_admin_manages_users_and_roles(self):
        r = self.client_for(self.pm).post("/api/users/", {"mobile": "9100000050", "name": "X", "password": PW},
                                          format="json")
        self.assertEqual(r.status_code, 403)
        c = self.client_for(self.admin)
        r = c.post("/api/roles/", {"key": "site-qa", "label": "Site QA", "permissions": ["indents.view"], "stages": ["receive"]},
                   format="json")
        self.assertEqual(r.status_code, 201, r.content)
        role_id = r.json()["id"]
        r = c.post("/api/users/", {"mobile": "9100000050", "name": "QA person", "password": PW, "role": role_id,
                                   "sites": [self.site.pk]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(User.objects.get(mobile="9100000050").check_password(PW))
        self.assertNotIn("password", r.json())

    def test_export_xlsx(self):
        self.raise_indent()
        r = self.client_for(self.mgmt).get("/api/indents/export/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("application/vnd.openxmlformats"))
