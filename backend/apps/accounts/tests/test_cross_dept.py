"""Approvals across departments: nobody approves their own work in any chain, people with two roles get exactly
the union of both, and a permission-matrix change applies on the very next request."""
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, User
from apps.indents.models import Indent
from apps.sites.models import Site

PW = "Str0ng-pass-123"
TODAY = timezone.localdate()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class CrossDepartment(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.site = Site.objects.create(code="TIM", name="Tridasha Imperial")
        cls.admin = User.objects.create_superuser("9876543210", PW, name="Admin")
        depts = {d: Department.objects.create(name=d) for d in ("Projects", "Stores", "Purchase", "Accounts", "Management")}
        cls.U = {}
        for n, (key, dept) in enumerate([("engineer", "Projects"), ("store", "Stores"), ("pm", "Projects"), ("pm2", "Projects"),
                                         ("management", "Management"), ("management2", "Management"), ("purchase", "Purchase"),
                                         ("accounts", "Accounts"), ("accounts2", "Accounts"), ("qs", "Projects")]):
            u = User.objects.create_user(f"97100000{n:02d}", PW, name=key, role=Role.objects.get(key=key.rstrip("2")),
                                         department=depts[dept])
            u.sites.add(cls.site)
            cls.U[key] = u
        # an engineer who also covers the store (two roles)
        cls.dual = User.objects.create_user("9710000099", PW, name="Engineer + Store", role=Role.objects.get(key="engineer"))
        cls.dual.extra_roles.add(Role.objects.get(key="store"))
        cls.dual.sites.add(cls.site)

    def setUp(self):
        cache.clear()

    def c(self, who):
        c = APIClient()
        c.force_authenticate(self.admin if who == "admin" else self.dual if who == "dual" else self.U[who])
        return c

    def act(self, who, iid, action, expect=200, **body):
        r = self.c(who).post(f"/api/indents/{iid}/act/", {"action": action, **body}, format="json")
        self.assertEqual(r.status_code, expect, (who, action, r.content[:300]))
        return r.json()

    def raise_by(self, who):
        r = self.c(who).post("/api/indents/", {"site": self.site.pk, "item": "Cement", "qty": 100, "est_rate": 400}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def test_indent_chain_nobody_approves_their_own(self):
        iid = self.raise_by("pm")                                   # the Project Head raises it
        self.act("store", iid, "approve")
        r = self.act("pm", iid, "approve", expect=400)              # can't approve own at 03
        self.assertIn("can’t", r["detail"])
        self.act("pm2", iid, "approve")                              # another Project Head can
        self.act("qs", iid, "approve", data={"boq_ref": "BOQ-1"})
        iid2 = self.raise_by("management")                          # a director raises one
        for who in ("store", "pm"):
            self.act(who, iid2, "approve")
        self.act("qs", iid2, "approve", data={"boq_ref": "BOQ-1"})
        self.act("management", iid2, "approve", expect=400)        # not their own budget
        d = self.act("admin", iid2, "approve", expect=400)         # admin needs a reason (override)
        self.assertIn("Remarks", d["detail"])
        self.act("admin", iid2, "approve", remarks="Second director on leave")
        self.assertTrue(Indent.objects.get(pk=iid2).history.filter(action="approve", override=True).exists())
        self.act("management2", iid, "approve")                     # the other indent: another director approves

    def test_bill_and_report_chains_nobody_approves_their_own(self):
        e = self.c("accounts").post("/api/expenses/", {"site": self.site.pk, "date": TODAY, "category": "Fuel",
                                                       "description": "d", "payee": "P", "amount": "100"}, format="json").json()
        self.c("accounts").post(f"/api/expenses/{e['id']}/submit/")
        self.assertEqual(self.c("accounts").post(f"/api/expenses/{e['id']}/approve/").status_code, 403)
        self.assertEqual(self.c("accounts2").post(f"/api/expenses/{e['id']}/approve/").status_code, 200)   # colleague in Accounts
        self.assertEqual(self.c("accounts2").post(f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "100"},
                                                  format="json").status_code, 403)                          # approver can't pay
        self.assertEqual(self.c("accounts").post(f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "100"},
                                                 format="json").status_code, 200)
        d = self.c("pm").post("/api/dpr/", {"site": self.site.pk, "date": TODAY, "summary": "x"}, format="json").json()
        self.c("pm").post(f"/api/dpr/{d['id']}/submit/")
        self.assertEqual(self.c("pm").post(f"/api/dpr/{d['id']}/approve/").status_code, 403)
        self.assertEqual(self.c("pm2").post(f"/api/dpr/{d['id']}/approve/").status_code, 200)

    def test_two_roles_give_the_union_and_nothing_more(self):
        me = self.c("dual").get("/api/auth/me/").json()
        self.assertTrue({"stock", "receive", "issue"} <= set(me["stages"]))      # store steps + engineer steps
        self.assertIn("materials.stock", me["permissions"])                       # from the store role
        self.assertIn("dpr.create", me["permissions"])                            # from the engineer role
        self.assertNotIn("expenses.view", me["permissions"])                      # neither role has finance
        iid = self.raise_by("engineer")
        self.act("dual", iid, "approve")                                          # acts as store at 02 on someone else's
        self.assertEqual(self.c("dual").get("/api/expenses/").status_code, 403)
        own = self.raise_by("dual")
        self.act("dual", own, "approve")         # stock check of own request is a verification, not an approval
        self.act("dual", own, "approve", expect=400)                              # but nothing at 03

    def test_matrix_change_applies_on_the_next_request_and_is_audited(self):
        from apps.audit.models import AuditLog
        store = APIClient()                     # a real signed-in session: the user is loaded fresh on every request
        self.assertEqual(store.post("/api/auth/login/", {"mobile": self.U["store"].mobile, "password": PW},
                                    format="json").status_code, 200)
        self.assertEqual(store.get("/api/reports/summary/").status_code, 403)
        role = Role.objects.get(key="store")
        perms = sorted(set(role.permissions) | {"reports.view"})
        r = self.c("admin").patch(f"/api/roles/{role.pk}/", {"permissions": perms}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(store.get("/api/reports/summary/").status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action__startswith="role").exists())
        r = self.c("admin").patch(f"/api/roles/{role.pk}/", {"permissions": sorted(set(perms) - {"reports.view"})},
                                  format="json")
        self.assertEqual(store.get("/api/reports/summary/").status_code, 403)
        # admin-only powers can't be handed to a role
        r = self.c("admin").patch(f"/api/roles/{role.pk}/", {"permissions": perms + ["team.manage"]}, format="json")
        self.assertNotIn("team.manage", Role.objects.get(pk=role.pk).permissions)

    def test_reports_split_spend_by_department(self):
        for who in ("accounts", "pm"):
            self.c(who).post("/api/expenses/", {"site": self.site.pk, "date": TODAY, "category": "Fuel", "description": "d",
                                                "payee": who, "amount": "100"}, format="json")
        rep = self.c("management").get("/api/reports/summary/").json()
        depts = {r["department"]: r["bills"] for r in rep["expenses"]["by_department"]}
        self.assertEqual(depts, {"Accounts": 1, "Projects": 1})
