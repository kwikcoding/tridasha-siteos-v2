"""Steps 11–12 money controls through the API, against the real database (PostgreSQL in CI)."""
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.indents.models import Indent, IndentEvent, WorkflowSettings
from apps.sites.models import Site

PW = "Str0ng-pass-123"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class MoneyControlsAPI(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.site = Site.objects.create(code="TIM", name="Tridasha Imperial")
        cls.admin = User.objects.create_superuser("9876543210", PW, name="Admin")
        cls.U = {}
        for n, role in enumerate(["engineer", "store", "pm", "management", "purchase", "accounts", "qs"]):
            u = User.objects.create_user(f"92000000{n:02d}", PW, name=role, role=Role.objects.get(key=role))
            u.sites.add(cls.site)
            cls.U[role] = u

    def setUp(self):
        cache.clear()

    def act(self, who, iid, action, expect=200, **body):
        c = APIClient()
        c.force_authenticate(self.admin if who == "admin" else self.U[who])
        r = c.post(f"/api/indents/{iid}/act/", {"action": action, **body}, format="json")
        self.assertEqual(r.status_code, expect, r.content)
        return r.json()

    def at_invoice(self):
        """100 bags at ₹400 on the PO, all received → PO × GRN = ₹40,000."""
        c = APIClient()
        c.force_authenticate(self.U["engineer"])
        iid = c.post("/api/indents/", {"site": self.site.pk, "item": "Cement", "unit": "bag", "qty": 100,
                                       "est_rate": 400}, format="json").json()["id"]
        for who, a, kw in [("store", "approve", {}), ("pm", "approve", {}), ("qs", "approve", {"data": {"boq_ref": "BOQ-1"}}), ("management", "approve", {}),
                           ("store", "purchase", {}), ("purchase", "approve", {"data": {"quotes": [{"vendor": "V", "rate": 400}]}}),
                           ("management", "approve", {"data": {"vendor_final": "V", "rate": "400"}}),
                           ("purchase", "po", {"data": {"po_no": "P1", "po_vendor": "V", "po_rate": "400"}}),
                           ("store", "receive", {"qty": 100, "data": {"grn_no": "G1"}})]:
            self.act(who, iid, a, **kw)
        return iid

    def at_payment(self, auth="47200"):
        iid = self.at_invoice()
        self.act("accounts", iid, "verifyInv", data={"inv_no": "INV-1", "inv_amount": "40000", "inv_gst": "7200"})
        self.act("management", iid, "authorizePay", data={"pay_auth_amount": auth})
        return iid

    def test_invoice_mismatch_refused_without_reason_and_recorded_with_it(self):
        iid = self.at_invoice()
        r = self.act("accounts", iid, "verifyInv", expect=400, data={"inv_no": "INV-1", "inv_amount": "45000"})
        self.assertIn("differs", r["detail"])
        d = self.act("accounts", iid, "verifyInv", remarks="Unloading charges agreed on call",
                     data={"inv_no": "INV-1", "inv_amount": "45000", "inv_gst": "8100"})
        self.assertEqual(d["pstage"], "payauth")
        self.assertEqual(float(d["inv_expected"]), 40000.0)
        self.assertEqual(d["money"]["variance"], 5000.0)
        self.assertFalse(d["money"]["within_tolerance"])
        self.assertEqual(d["money"]["payable"], 53100.0)
        self.assertEqual(IndentEvent.objects.get(indent_id=iid, action="verifyInv").remarks,
                         "Unloading charges agreed on call")

    def test_authorise_more_than_invoice_refused(self):
        iid = self.at_invoice()
        self.act("accounts", iid, "verifyInv", data={"inv_no": "INV-1", "inv_amount": "40000", "inv_gst": "7200"})
        r = self.act("management", iid, "authorizePay", expect=400, data={"pay_auth_amount": "47201"})
        self.assertIn("more than the verified invoice", r["detail"])
        self.act("management", iid, "authorizePay", expect=400)            # amount required
        d = self.act("management", iid, "authorizePay", data={"pay_auth_amount": "47200"})
        self.assertEqual(float(d["pay_auth_amount"]), 47200.0)

    def test_part_payments_excess_and_duplicate_reference(self):
        iid = self.at_payment()
        d = self.act("accounts", iid, "pay", data={"paid_on": "2026-10-20", "pay_amount": "20000", "pay_ref": "UTR1"})
        self.assertEqual((d["pstage"], d["pstatus"], float(d["paid_total"])), ("payment", "Part Paid", 20000.0))
        self.assertEqual(d["money"]["outstanding"], 27200.0)
        r = self.act("accounts", iid, "pay", expect=400,
                     data={"paid_on": "2026-10-21", "pay_amount": "1000", "pay_ref": "UTR1"})
        self.assertIn("duplicate", r["detail"])
        r = self.act("accounts", iid, "pay", expect=400,
                     data={"paid_on": "2026-10-21", "pay_amount": "27200.01", "pay_ref": "UTR2"})
        self.assertIn("excess", r["detail"])
        d = self.act("accounts", iid, "pay", data={"paid_on": "2026-10-21", "pay_amount": "27200", "pay_ref": "UTR2"})
        self.assertEqual((d["pstage"], d["pstatus"], float(d["paid_total"])), ("closed", "Purchase Closed", 47200.0))
        self.assertEqual(d["money"]["outstanding"], 0)
        self.act("accounts", iid, "pay", expect=400, data={"paid_on": "2026-10-22", "pay_amount": "1"})   # closed
        self.assertEqual(IndentEvent.objects.filter(indent_id=iid, action="pay").count(), 2)

    def test_negative_amounts_refused(self):
        iid = self.at_payment()
        self.act("accounts", iid, "pay", expect=400, data={"paid_on": "2026-10-20", "pay_amount": "-5"})
        self.assertIsNone(Indent.objects.get(pk=iid).paid_total)

    def test_tolerance_setting_admin_only_bounded_and_audited(self):
        c = APIClient()
        c.force_authenticate(self.U["accounts"])
        self.assertEqual(c.put("/api/workflow/settings/", {"inv_tolerance_pct": 5}, format="json").status_code, 403)
        c.force_authenticate(self.admin)
        self.assertEqual(c.put("/api/workflow/settings/", {"inv_tolerance_pct": 30}, format="json").status_code, 400)
        r = c.put("/api/workflow/settings/", {"inv_tolerance_pct": "15"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["settings"]["inv_tolerance_pct"], 15.0)
        self.assertEqual(float(WorkflowSettings.load().inv_tolerance_pct), 15.0)
        self.assertTrue(AuditLog.objects.filter(action="workflow.settings").exists())
        iid = self.at_invoice()
        self.act("accounts", iid, "verifyInv", data={"inv_no": "INV-1", "inv_amount": "45000"})   # within 15 %

    def test_raised_open_counts_beyond_first_page(self):
        c = APIClient()
        c.force_authenticate(self.U["engineer"])
        for _ in range(55):            # more than one page of 50
            c.post("/api/indents/", {"site": self.site.pk, "item": "Sand", "unit": "cum", "qty": 1}, format="json")
        first = Indent.objects.filter(raised_by=self.U["engineer"]).first()
        self.act("engineer", first.pk, "cancel", remarks="Not needed")
        p = c.get("/api/auth/pending/").json()
        self.assertEqual(p["raised_open"], 54)
        self.assertEqual(Indent.objects.filter(raised_by=self.U["engineer"]).values("number").distinct().count(), 55)

    def test_no_new_indent_on_closed_site_or_unassigned_site(self):
        c = APIClient()
        c.force_authenticate(self.U["engineer"])
        other = Site.objects.create(code="OTH", name="Other")
        r = c.post("/api/indents/", {"site": other.pk, "item": "Sand", "unit": "cum", "qty": 1}, format="json")
        self.assertEqual(r.status_code, 400)
        self.site.active = False
        self.site.save()
        r = c.post("/api/indents/", {"site": self.site.pk, "item": "Sand", "unit": "cum", "qty": 1}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("closed", str(r.content.decode()))
