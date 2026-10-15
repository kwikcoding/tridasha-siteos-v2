"""Access control acceptance tests: one login per role, server-side enforcement, audit."""
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, User
from apps.audit.models import AuditLog
from apps.indents.models import Indent
from apps.materials.models import Material, StockEntry
from apps.sites.models import Site

PW = "Str0ng-pass-123"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class AccessControl(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.site = Site.objects.create(code="TIM", name="Tridasha Imperial")
        cls.site_b = Site.objects.create(code="VAR", name="Varuna")
        cls.admin = User.objects.create_superuser("9876543210", PW, name="Admin")
        U = {}
        for i, key in enumerate(["engineer", "supervisor", "store", "pm", "management", "purchase", "accounts", "qs",
                                 "safety", "viewer"]):
            u = User.objects.create_user(f"93000000{i:02d}", PW, name=key.title(), role=Role.objects.get(key=key))
            u.sites.add(cls.site)
            U[key] = u
        cls.U = U
        cls.cement = Material.objects.create(code="CEM", name="Cement", unit="bag", std_rate=400)

    def setUp(self):
        cache.clear()

    def c(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def raise_indent(self, user="engineer", site=None, **kw):
        r = self.c(self.U[user]).post("/api/indents/", {"site": (site or self.site).pk, "item": "Cement", "unit": "bag",
                                                        "qty": 10, "est_rate": 400, **kw}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def act(self, who, iid, action, expect=200, **body):
        user = self.admin if who == "admin" else self.U[who]
        r = self.c(user).post(f"/api/indents/{iid}/act/", {"action": action, **body}, format="json")
        self.assertEqual(r.status_code, expect, r.content)
        return r.json()

    # 1 — administrator manages staff and roles; nobody else can
    def test_admin_manages_staff_roles_departments(self):
        a = self.c(self.admin)
        d = a.post("/api/departments/", {"name": "Stores"}, format="json")
        self.assertEqual(d.status_code, 201, d.content)
        r = a.post("/api/users/", {"mobile": "9300000099", "name": "New Store", "password": PW, "employee_id": "tdi-042",
                                   "designation": "Store Assistant", "department": d.json()["id"],
                                   "reporting_manager": self.U["store"].pk, "role": Role.objects.get(key="store").pk,
                                   "extra_roles": [Role.objects.get(key="qs").pk], "sites": [self.site.pk]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        u = User.objects.get(mobile="9300000099")
        self.assertEqual((u.employee_id, u.must_change_password), ("TDI-042", True))
        self.assertEqual(sorted(x.key for x in u.all_roles()), ["qs", "store"])
        self.assertTrue(AuditLog.objects.filter(action="user.create", target_id=str(u.pk)).exists())
        for k in ("pm", "qs", "management", "store"):
            self.assertEqual(self.c(self.U[k]).post("/api/users/", {"mobile": "9300000098", "name": "X", "password": PW},
                                                    format="json").status_code, 403)
            self.assertEqual(self.c(self.U[k]).patch(f"/api/roles/{Role.objects.get(key=k).pk}/",
                                                     {"permissions": ["team.view"]}, format="json").status_code, 403)

    def test_admin_only_permissions_cannot_be_granted(self):
        r = self.c(self.admin).patch(f"/api/roles/{Role.objects.get(key='pm').pk}/", {"permissions": ["team.manage"]},
                                     format="json")
        self.assertEqual(r.status_code, 400)
        r = self.c(self.admin).patch(f"/api/roles/{Role.objects.get(key='admin').pk}/", {"label": "X"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cannot_change_own_role(self):
        r = self.c(self.admin).patch(f"/api/users/{self.admin.pk}/", {"role": Role.objects.get(key="viewer").pk},
                                     format="json")
        self.assertEqual(r.status_code, 400)

    # 2-8 — each role acts only at its own steps
    def test_each_role_only_at_its_steps(self):
        iid = self.raise_indent()
        for k in ("pm", "management", "purchase", "accounts", "qs", "supervisor", "viewer"):
            self.act(k, iid, "approve", expect=400 if k != "safety" else 403)
        self.act("store", iid, "approve")                      # 02
        self.act("store", iid, "approve", expect=400)          # store can't do 03
        self.act("pm", iid, "approve")                         # 03
        self.act("management", iid, "approve", expect=400)    # 04a belongs to QS
        self.act("qs", iid, "approve", data={"boq_ref": "BOQ-1"})
        self.act("qs", iid, "approve", expect=400)            # QS cannot approve 04b
        self.act("management", iid, "approve")                 # 04b
        self.act("store", iid, "purchase")                     # stock check
        self.act("purchase", iid, "approve", data={"quotes": [{"vendor": "V", "rate": 400}]})   # 05
        self.act("purchase", iid, "approve", expect=400, data={"vendor_final": "V", "rate": "400"})
        self.act("management", iid, "approve", data={"vendor_final": "V", "rate": "400"})        # 06
        self.act("purchase", iid, "po", data={"po_no": "P1", "po_vendor": "V"})                  # 07
        self.act("engineer", iid, "receive", qty=10, data={"grn_no": "G1"})                      # 09
        self.act("engineer", iid, "issueClose")                                                   # 10 (engineer may close)
        # 11: purchase may only hold / return; accountant verifies
        self.act("purchase", iid, "verifyInv", expect=400, data={"inv_no": "I", "inv_amount": "4000"})
        self.act("accounts", iid, "verifyInv", data={"inv_no": "I", "inv_amount": "4000"})
        # 12a management authorises; accountant can't
        self.act("accounts", iid, "authorizePay", expect=400)
        self.act("accounts", iid, "pay", expect=400, data={"paid_on": "2026-10-20"})
        self.act("management", iid, "authorizePay", data={"pay_auth_amount": "4000"})
        self.act("management", iid, "pay", expect=400, data={"paid_on": "2026-10-20", "pay_amount": "4000"})   # 12b isn't theirs
        d = self.act("accounts", iid, "pay", data={"paid_on": "2026-10-20", "pay_amount": "4000"})
        self.assertEqual(d["pstatus"], "Purchase Closed")

    def test_supervisor_raises_qs_and_safety_cannot(self):
        self.raise_indent("supervisor")
        self.assertEqual(self.c(self.U["qs"]).post("/api/indents/", {"site": self.site.pk, "item": "X", "qty": 1},
                                                   format="json").status_code, 403)
        self.assertEqual(self.c(self.U["qs"]).get("/api/indents/").status_code, 200)        # QS can read
        self.assertEqual(self.c(self.U["safety"]).get("/api/indents/").status_code, 403)    # safety has no indents
        self.assertEqual(self.c(self.U["safety"]).get("/api/materials/").status_code, 403)

    # 11-12 — unauthorised APIs are refused regardless of the UI
    def test_unauthorised_api_calls(self):
        e = self.c(self.U["engineer"])
        self.assertEqual(e.get("/api/users/").status_code, 403)
        self.assertEqual(e.get("/api/audit/").status_code, 403)
        self.assertEqual(e.put("/api/workflow/settings/", {"stages": {}}, format="json").status_code, 403)
        self.assertEqual(e.post("/api/stock/", {"site": self.site.pk, "material": self.cement.pk, "kind": "IN", "qty": 5},
                                format="json").status_code, 403)     # engineer has no materials.stock
        s = self.c(self.U["store"])
        self.assertEqual(s.post("/api/stock/", {"site": self.site.pk, "material": self.cement.pk, "kind": "IN", "qty": 5},
                                format="json").status_code, 201)
        self.assertEqual(self.c(self.U["viewer"]).get("/api/indents/export/").status_code, 200)   # viewer may export
        self.assertEqual(self.c(self.U["safety"]).get("/api/indents/export/").status_code, 403)

    def test_permission_change_takes_effect(self):
        safety = Role.objects.get(key="safety")
        r = self.c(self.admin).patch(f"/api/roles/{safety.pk}/", {"permissions": safety.permissions + ["indents.view"]},
                                     format="json")
        self.assertEqual(r.status_code, 200, r.content)
        fresh = User.objects.get(pk=self.U["safety"].pk)
        self.assertEqual(self.c(fresh).get("/api/indents/").status_code, 200)
        me = self.c(fresh).get("/api/auth/me/").json()
        self.assertIn("indents", me["modules_view"])
        self.assertTrue(AuditLog.objects.filter(action="role.update", target_id=str(safety.pk)).exists())

    def test_multiple_roles_combine(self):
        u = User.objects.get(pk=self.U["qs"].pk)
        u.extra_roles.add(Role.objects.get(key="store"))
        u = User.objects.get(pk=u.pk)
        iid = self.raise_indent()
        r = self.c(u).post(f"/api/indents/{iid}/act/", {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    # 13 — one site's people can't reach another site's records
    def test_site_scope(self):
        other = self.raise_indent("engineer")
        b_eng = User.objects.create_user("9300000077", PW, name="B engineer", role=Role.objects.get(key="engineer"))
        b_eng.sites.add(self.site_b)
        self.assertEqual(self.c(b_eng).get(f"/api/indents/{other}/").status_code, 404)
        b_store = User.objects.create_user("9300000078", PW, name="B store", role=Role.objects.get(key="store"))
        b_store.sites.add(self.site_b)
        self.assertEqual(self.c(b_store).post(f"/api/indents/{other}/act/", {"action": "approve"}, format="json").status_code, 404)
        self.assertEqual(self.c(b_store).get(f"/api/stock/balances/?site={self.site.pk}").status_code, 403)

    # 14 — pending counts
    def test_pending_counts(self):
        self.raise_indent()
        self.raise_indent()
        self.assertEqual(self.c(self.U["store"]).get("/api/auth/pending/").json()["indents"], 2)
        self.assertEqual(self.c(self.U["pm"]).get("/api/auth/pending/").json()["indents"], 0)
        Material.objects.filter(pk=self.cement.pk).update(reorder_level=50)
        StockEntry.objects.create(site=self.site, material=self.cement, kind="IN", qty=20, by=self.U["store"],
                                  date="2026-10-01")
        self.assertEqual(self.c(self.U["store"]).get("/api/auth/pending/").json()["low_stock"], 1)

    # 16 — overrides need a reason and are audited
    def test_admin_override_is_logged(self):
        iid = self.raise_indent()
        r = self.act("admin", iid, "approve", expect=400)
        self.assertIn("reason", r["detail"])
        d = self.act("admin", iid, "approve", remarks="Store keeper on leave today")
        self.assertTrue(d["history"][-1]["override"])
        log = AuditLog.objects.get(action="indent.override")
        self.assertEqual(log.actor_id, self.admin.pk)
        self.assertIn("leave", log.changes["remarks"])
        # the admin can raise and act on their own request without it being an override
        self.assertEqual(Indent.objects.get(pk=iid).history.filter(override=True).count(), 1)

    def test_authoriser_cannot_settle_even_admin(self):
        iid = self.raise_indent()
        for who, a, kw in [("store", "approve", {}), ("pm", "approve", {}), ("qs", "approve", {"data": {"boq_ref": "BOQ-1"}}), ("management", "approve", {}),
                           ("store", "purchase", {}), ("purchase", "approve", {"data": {"quotes": [{"vendor": "V", "rate": 1}]}}),
                           ("management", "approve", {"data": {"vendor_final": "V", "rate": "1"}}),
                           ("purchase", "po", {"data": {"po_no": "P", "po_vendor": "V"}}),
                           ("store", "receive", {"qty": 10}), ("accounts", "verifyInv", {"data": {"inv_no": "I", "inv_amount": "10"}})]:
            self.act(who, iid, a, **kw)
        self.act("admin", iid, "authorizePay", remarks="Director travelling", data={"pay_auth_amount": "10"})
        r = self.act("admin", iid, "pay", expect=400, remarks="x", data={"paid_on": "2026-10-20", "pay_amount": "10"})
        self.assertIn("can’t", r["detail"])

    # login history + forced password change after reset (real session, so the middleware runs)
    def test_login_history_and_forced_password_change(self):
        c = APIClient()
        self.assertEqual(c.post("/api/auth/login/", {"mobile": self.U["store"].mobile, "password": "wrong"},
                                format="json").status_code, 400)
        self.assertTrue(AuditLog.objects.filter(action="login.failed").exists())
        r = self.c(self.admin).post(f"/api/users/{self.U['store'].pk}/reset-password/", {"password": "Temp-pass-777"},
                                    format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["must_change_password"])
        c = APIClient()
        r = c.post("/api/auth/login/", {"mobile": self.U["store"].mobile, "password": "Temp-pass-777"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["must_change_password"])
        blocked = c.get("/api/indents/")
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()["code"], "password_change_required")
        c.get("/api/auth/csrf/")
        r = c.post("/api/auth/password/", {"current": "Temp-pass-777", "new": "My-own-pass-2026"}, format="json",
                   HTTP_X_CSRFTOKEN=c.cookies["csrftoken"].value)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(c.get("/api/indents/").status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="login.success", actor=self.U["store"]).exists())
        self.assertTrue(AuditLog.objects.filter(action="password.reset").exists())

    def test_permission_catalogue_and_me(self):
        cat = self.c(self.U["pm"]).get("/api/permissions/").json()
        self.assertTrue(any(m["key"] == "materials" for g in cat["modules"] for m in g["modules"]))
        self.assertTrue(any(s["key"] == "payauth" for s in cat["steps"]))
        me = self.c(self.U["management"]).get("/api/auth/me/").json()
        self.assertIn("payauth", me["stages"])
        self.assertNotIn("payment", me["stages"])
