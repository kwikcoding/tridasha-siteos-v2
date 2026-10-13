"""API tests for the site-work modules: projects, tasks, daily progress, labour, expenses, quality & safety,
documents, plant & equipment and reports — each with the role rules, site isolation and business rules."""
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.alerts.models import Notification
from apps.audit.models import AuditLog
from apps.sites.models import Project, Site

PW = "Str0ng-pass-123"
MEDIA = tempfile.mkdtemp(prefix="siteos-test-media-")
TODAY = timezone.localdate()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, MEDIA_ROOT=MEDIA)
class ModulesBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.site = Site.objects.create(code="TIM", name="Tridasha Imperial")
        cls.other = Site.objects.create(code="VAR", name="Varuna")
        cls.admin = User.objects.create_superuser("9876543210", PW, name="Admin")
        cls.U = {}
        for n, key in enumerate(["engineer", "supervisor", "store", "pm", "management", "purchase", "accounts", "qs",
                                 "safety", "viewer"]):
            u = User.objects.create_user(f"96000000{n:02d}", PW, name=key.title(), role=Role.objects.get(key=key))
            u.sites.add(cls.site)
            cls.U[key] = u
        # a supervisor who works only at the other site
        cls.far = User.objects.create_user("9600000099", PW, name="Far Supervisor", role=Role.objects.get(key="supervisor"))
        cls.far.sites.add(cls.other)
        cls.tower = Project.objects.create(site=cls.site, code="TA", name="Tower A", budget=Decimal("1000000"))
        cls.other_project = Project.objects.create(site=cls.other, code="V1", name="Varuna Block 1")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()

    def c(self, who):
        c = APIClient()
        c.force_authenticate(self.admin if who == "admin" else self.far if who == "far" else self.U[who])
        return c

    def call(self, who, method, url, data=None, expect=200, fmt="json"):
        r = getattr(self.c(who), method)(url, data or {}, format=fmt) if method != "get" else self.c(who).get(url, data or {})
        self.assertEqual(r.status_code, expect, (who, method, url, r.content[:400]))
        return r.json() if r.get("content-type", "").startswith("application/json") else r


class ProjectsTests(ModulesBase):
    def test_create_edit_and_permissions(self):
        d = self.call("pm", "post", "/api/projects/", {"site": self.site.pk, "code": "tb", "name": "Tower B",
                                                       "start_date": "2026-01-01", "end_date": "2027-06-30"}, 201)
        self.assertEqual(d["code"], "TB")
        self.call("store", "post", "/api/projects/", {"site": self.site.pk, "code": "X", "name": "X"}, 403)
        self.call("pm", "post", "/api/projects/", {"site": self.site.pk, "code": "TB", "name": "Dup"}, 400)
        self.call("pm", "post", "/api/projects/", {"site": self.site.pk, "code": "TC", "name": "Bad dates",
                                                   "start_date": "2027-01-01", "end_date": "2026-01-01"}, 400)
        self.call("pm", "patch", f"/api/projects/{d['id']}/", {"status": "completed"})
        self.assertTrue(AuditLog.objects.filter(action="sites.update").exists())
        # every signed-in person can list projects at their own sites only
        names = [p["code"] for p in self.call("store", "get", "/api/projects/")]
        self.assertIn("TA", names)
        self.assertNotIn("V1", names)

    def test_indent_and_stock_carry_project(self):
        r = self.call("engineer", "post", "/api/indents/", {"site": self.site.pk, "project": self.other_project.pk,
                                                            "item": "Sand", "qty": 1}, 400)
        self.assertIn("another site", str(r))
        d = self.call("engineer", "post", "/api/indents/", {"site": self.site.pk, "project": self.tower.pk,
                                                            "item": "Sand", "qty": 1}, 201)
        self.assertEqual(d["project"], self.tower.pk)
        done = Project.objects.create(site=self.site, code="OLD", name="Old", status="completed")
        self.call("engineer", "post", "/api/indents/", {"site": self.site.pk, "project": done.pk, "item": "S", "qty": 1}, 400)


class TasksTests(ModulesBase):
    def test_assign_rules_dependencies_progress_and_overdue(self):
        late = (TODAY - timedelta(days=3)).isoformat()
        # the engineer can create tasks but can assign only to themself
        self.call("engineer", "post", "/api/tasks/", {"site": self.site.pk, "title": "Shuttering",
                                                      "assignee": self.U["supervisor"].pk}, 400)
        with self.captureOnCommitCallbacks(execute=True):
            first = self.call("pm", "post", "/api/tasks/", {"site": self.site.pk, "project": self.tower.pk,
                                                            "title": "Rebar check", "assignee": self.U["supervisor"].pk,
                                                            "due_date": late}, 201)
        self.assertTrue(first["overdue"])
        self.assertEqual(first["days_overdue"], 3)
        self.assertTrue(Notification.objects.filter(user=self.U["supervisor"], title__contains="Rebar check").exists())
        # can't assign someone who isn't on the site
        self.call("pm", "post", "/api/tasks/", {"site": self.site.pk, "title": "X", "assignee": self.far.pk}, 400)
        second = self.call("pm", "post", "/api/tasks/", {"site": self.site.pk, "title": "Pour slab",
                                                         "depends_on": first["id"]}, 201)
        r = self.call("pm", "patch", f"/api/tasks/{second['id']}/", {"status": "done"}, 400)
        self.assertIn("first", str(r))
        self.call("pm", "patch", f"/api/tasks/{first['id']}/", {"depends_on": second["id"]}, 400)   # loop
        # the assignee updates progress without edit rights; someone else can't
        self.call("viewer", "post", f"/api/tasks/{first['id']}/progress/", {"status": "in_progress"}, 403)
        d = self.call("supervisor", "post", f"/api/tasks/{first['id']}/progress/", {"status": "done"})
        self.assertEqual((d["status"], d["progress"], d["overdue"]), ("done", 100, False))
        self.call("pm", "patch", f"/api/tasks/{second['id']}/", {"status": "done"})
        self.assertEqual(len(rowsof(self.call("pm", "get", "/api/tasks/", {"overdue": "1"}))), 0)
        self.call("store", "get", "/api/tasks/", expect=403)          # store keeper has no tasks module
        self.call("far", "get", f"/api/tasks/{first['id']}/", expect=404)   # other site


class DailyProgressTests(ModulesBase):
    def body(self, **kw):
        return {"site": self.site.pk, "project": self.tower.pk, "date": TODAY.isoformat(), "summary": "Slab L5 poured",
                "work_items": [{"activity": "RCC slab", "qty": 42.5, "unit": "cum"}],
                "manpower": [{"trade": "Mason", "count": 12}, {"trade": "Helper", "count": 20}], **kw}

    def test_one_per_day_submit_approve_lock(self):
        d = self.call("engineer", "post", "/api/dpr/", self.body(), 201)
        self.assertEqual((d["status"], d["manpower_total"]), ("draft", 32))
        self.call("engineer", "post", "/api/dpr/", self.body(), 400)                  # duplicate day
        self.call("engineer", "post", "/api/dpr/", self.body(date=(TODAY + timedelta(days=1)).isoformat()), 400)
        self.call("engineer", "post", "/api/dpr/", self.body(work_items=[{"activity": "x", "qty": -1}]), 400)
        self.call("store", "post", "/api/dpr/", self.body(project=None), 403)         # store can only view
        self.call("engineer", "post", f"/api/dpr/{d['id']}/submit/")
        self.call("engineer", "patch", f"/api/dpr/{d['id']}/", {"summary": "changed"}, 400)   # locked once submitted
        self.call("engineer", "post", f"/api/dpr/{d['id']}/approve/", expect=403)     # no dpr.approve
        self.call("pm", "post", f"/api/dpr/{d['id']}/send-back/", expect=400)         # needs a note
        self.call("pm", "post", f"/api/dpr/{d['id']}/send-back/", {"note": "Add rebar quantity"})
        self.call("engineer", "patch", f"/api/dpr/{d['id']}/", {"summary": "Slab L5 poured; 2.1 t rebar"})
        self.call("engineer", "post", f"/api/dpr/{d['id']}/submit/")
        d = self.call("pm", "post", f"/api/dpr/{d['id']}/approve/")
        self.assertEqual(d["status"], "approved")
        s = self.call("pm", "get", "/api/dpr/summary/")
        self.assertEqual((s[0]["reports"], s[0]["approved"], s[0]["activities"]["RCC slab (cum)"]), (1, 1, 42.5))

    def test_cannot_approve_own_report(self):
        d = self.call("pm", "post", "/api/dpr/", self.body(project=None), 201)
        self.call("pm", "post", f"/api/dpr/{d['id']}/submit/")
        self.call("pm", "post", f"/api/dpr/{d['id']}/approve/", expect=403)


class LabourTests(ModulesBase):
    def test_roll_mark_wages_approve_lock(self):
        w1 = self.call("supervisor", "post", "/api/workers/", {"site": self.site.pk, "name": "Ramesh", "trade": "Mason",
                                                               "contractor": "Sai Labour", "daily_wage": "900", "ot_rate": "120",
                                                               "worker_code": "M-01"}, 201)
        w2 = self.call("supervisor", "post", "/api/workers/", {"site": self.site.pk, "name": "Suresh", "trade": "Helper",
                                                               "daily_wage": "650"}, 201)
        self.call("supervisor", "post", "/api/workers/", {"site": self.site.pk, "name": "Dup", "worker_code": "M-01"}, 400)
        self.call("supervisor", "post", "/api/workers/", {"site": self.site.pk, "name": "Neg", "daily_wage": "-1"}, 400)
        far_worker = self.call("far", "post", "/api/workers/", {"site": self.other.pk, "name": "Far"}, 201)
        day = (TODAY - timedelta(days=1)).isoformat()
        url = "/api/attendance/mark/"
        base = {"site": self.site.pk, "project": self.tower.pk, "date": day}
        self.call("supervisor", "post", url, {**base, "entries": [{"worker": w1["id"], "status": "absent", "ot_hours": 2}]}, 400)
        self.call("supervisor", "post", url, {**base, "entries": [{"worker": w1["id"], "status": "present"},
                                                                  {"worker": w1["id"], "status": "half"}]}, 400)
        self.call("supervisor", "post", url, {**base, "entries": [{"worker": far_worker["id"], "status": "present"}]}, 400)
        self.call("supervisor", "post", url, {**base, "date": (TODAY + timedelta(days=1)).isoformat(),
                                              "entries": [{"worker": w1["id"], "status": "present"}]}, 400)
        marks = self.call("supervisor", "post", url, {**base, "entries": [
            {"worker": w1["id"], "status": "present", "ot_hours": 2}, {"worker": w2["id"], "status": "half"}]}, 201)
        self.assertEqual(sorted(Decimal(m["wage"]) for m in marks), [Decimal("325.00"), Decimal("1140.00")])
        # marking again corrects the same day (no duplicates)
        self.call("supervisor", "post", url, {**base, "entries": [{"worker": w2["id"], "status": "present"}]}, 201)
        s = self.call("supervisor", "get", "/api/attendance/summary/", {"site": self.site.pk})
        self.assertEqual((float(s["man_days"]), float(s["total_wages"])), (2.0, 1790.0))
        self.call("supervisor", "post", "/api/attendance/approve-day/", {"site": self.site.pk, "date": day}, 403)
        self.assertEqual(self.call("pm", "post", "/api/attendance/approve-day/", {"site": self.site.pk, "date": day})["approved"], 2)
        r = self.call("supervisor", "post", url, {**base, "entries": [{"worker": w1["id"], "status": "absent"}]}, 400)
        self.assertIn("locked", str(r))
        mark = self.call("supervisor", "get", "/api/attendance/", {"worker": w1["id"]})["results"][0]
        self.call("supervisor", "patch", f"/api/attendance/{mark['id']}/", {"status": "absent"}, 400)
        self.call("accounts", "get", "/api/attendance/export/")                      # accountant sees labour
        self.call("purchase", "get", "/api/attendance/", expect=403)


class ExpensesTests(ModulesBase):
    def bill(self, **kw):
        return {"site": self.site.pk, "project": self.tower.pk, "date": TODAY.isoformat(), "category": "Equipment hire",
                "description": "JCB 3DX — 6 days", "payee": "Balaji Earthmovers", "bill_no": "BE-118",
                "amount": "60000", "gst": "10800", **kw}

    def test_approve_pay_controls(self):
        e = self.call("accounts", "post", "/api/expenses/", self.bill(), 201)
        self.assertEqual(Decimal(e["total"]), Decimal("70800.00"))
        self.call("accounts", "post", "/api/expenses/", self.bill(payee="balaji earthmovers"), 400)   # same bill again
        self.call("safety", "get", "/api/expenses/", expect=403)                 # finance hidden from safety
        self.call("accounts", "post", f"/api/expenses/{e['id']}/submit/")
        self.call("accounts", "patch", f"/api/expenses/{e['id']}/", {"amount": "1"}, 400)        # locked
        self.call("accounts", "post", f"/api/expenses/{e['id']}/approve/", expect=403)           # own bill
        self.call("management", "post", f"/api/expenses/{e['id']}/approve/", {"approved_amount": "70801"}, 400)
        self.call("management", "post", f"/api/expenses/{e['id']}/approve/", {"approved_amount": "65000"})
        self.call("management", "post", f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "1"}, 403)  # no edit
        self.call("accounts", "post", f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "65000.01"}, 400)
        d = self.call("accounts", "post", f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "40000", "ref": "UTR77"})
        self.assertEqual((d["status"], Decimal(d["outstanding"])), ("part_paid", Decimal("25000.00")))
        self.call("accounts", "post", f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "100", "ref": "UTR77"}, 400)
        d = self.call("accounts", "post", f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "25000", "ref": "UTR78"})
        self.assertEqual((d["status"], len(d["payments"])), ("paid", 2))
        self.call("accounts", "post", f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "1"}, 400)

    def test_approver_cannot_pay_and_reject_needs_note(self):
        e = self.call("pm", "post", "/api/expenses/", self.bill(bill_no="X-1"), 201)
        self.call("pm", "post", f"/api/expenses/{e['id']}/submit/")
        self.call("accounts", "post", f"/api/expenses/{e['id']}/reject/", expect=400)
        self.call("accounts", "post", f"/api/expenses/{e['id']}/approve/")
        r = self.call("accounts", "post", f"/api/expenses/{e['id']}/pay/", {"date": TODAY, "amount": "10"}, 403)
        self.assertIn("approved", r["detail"])
        s = self.call("accounts", "get", "/api/expenses/summary/")
        self.assertEqual(float(s["totals"]["approved"]), 70800.0)


class QualityTests(ModulesBase):
    def test_ncr_needs_action_and_evidence_to_close(self):
        o = self.call("safety", "post", "/api/observations/", {"site": self.site.pk, "kind": "ncr", "title": "Honeycombing at C4",
                                                                "severity": "high", "assigned_to": self.U["engineer"].pk,
                                                                "due_date": TODAY.isoformat()}, 201)
        self.assertTrue(o["ref_no"].startswith("NCR-"))
        self.assertTrue(o["needs_evidence"])
        url = f"/api/observations/{o['id']}/"
        self.call("safety", "post", url + "close/", {"note": "Repaired"}, 400)            # no corrective action
        self.call("engineer", "patch", url, {"corrective_action": "Chip out, grout with GP2"})
        self.call("engineer", "post", url + "close/", {"note": "Done"}, 403)             # needs quality.approve
        r = self.call("safety", "post", url + "close/", {"note": "Repaired"}, 400)
        self.assertIn("evidence", r["detail"])
        bad = SimpleUploadedFile("run.exe", b"MZ", content_type="application/octet-stream")
        self.call("engineer", "post", url + "attach/", {"file": bad, "purpose": "evidence"}, 400, fmt="multipart")
        img = SimpleUploadedFile("after.jpg", b"\xff\xd8\xff fake jpeg", content_type="image/jpeg")
        a = self.call("engineer", "post", url + "attach/", {"file": img, "purpose": "evidence"}, 201, fmt="multipart")
        f = self.c("safety").get(f"/api{a['url']}")
        self.assertEqual(f.status_code, 200)
        self.assertEqual(self.c("far").get(f"/api{a['url']}").status_code, 404)          # other site can't fetch it
        d = self.call("safety", "post", url + "close/", {"note": "Repaired and checked"})
        self.assertEqual(d["status"], "closed")
        self.call("engineer", "patch", url, {"title": "x"}, 400)                          # closed is locked
        self.call("safety", "post", url + "reopen/", expect=400)
        self.call("safety", "post", url + "reopen/", {"note": "Crack reappeared"})

    def test_low_severity_observation_closes_without_evidence(self):
        o = self.call("supervisor", "post", "/api/observations/", {"site": self.site.pk, "kind": "safety",
                                                                    "title": "Helmet not worn", "severity": "low",
                                                                    "corrective_action": "Toolbox talk"}, 201)
        self.call("safety", "post", f"/api/observations/{o['id']}/close/", {"note": "Briefed the gang"})
        self.call("purchase", "get", "/api/observations/", expect=403)


class DocumentsTests(ModulesBase):
    def test_revisions_never_replace_and_archive_not_delete(self):
        d = self.call("engineer", "post", "/api/documents/", {"site": self.site.pk, "project": self.tower.pk,
                                                               "category": "drawing", "number": "TA-STR-101",
                                                               "title": "Typical floor slab"}, 201)
        self.call("engineer", "post", "/api/documents/", {"site": self.site.pk, "category": "drawing",
                                                          "number": "ta-str-101", "title": "dup"}, 400)
        url = f"/api/documents/{d['id']}/"
        f0 = SimpleUploadedFile("slab-r0.pdf", b"%PDF-1.4 r0", content_type="application/pdf")
        r0 = self.call("engineer", "post", url + "upload/", {"file": f0}, 201, fmt="multipart")
        self.assertEqual(r0["rev"], "R0")
        again = SimpleUploadedFile("slab.pdf", b"%PDF-1.4 other", content_type="application/pdf")
        self.call("engineer", "post", url + "upload/", {"file": again, "rev": "R0"}, 400, fmt="multipart")
        f1 = SimpleUploadedFile("slab-r1.pdf", b"%PDF-1.4 r1", content_type="application/pdf")
        self.call("engineer", "post", url + "upload/", {"file": f1, "note": "Beam B4 deepened"}, 201, fmt="multipart")
        doc = self.call("safety", "get", url)
        self.assertEqual((doc["current_rev"], [r["status"] for r in doc["revisions"]]), ("R1", ["For construction", "Superseded"]))
        dl = self.c("safety").get(f"{url}revisions/{r0['id']}/download/")
        self.assertEqual(b"".join(dl.streaming_content), b"%PDF-1.4 r0")              # the old file is intact
        self.call("qs", "get", "/api/documents/", expect=403)
        self.call("engineer", "delete", url, expect=403)                                   # no docs.delete
        self.call("pm", "post", url + "archive/", expect=403)                              # only docs.delete may archive
        self.call("admin", "delete", url, expect=400)                                      # has files → archive instead
        self.call("admin", "post", url + "archive/")
        self.assertEqual(rowsof(self.call("pm", "get", "/api/documents/")), [])


class EquipmentTests(ModulesBase):
    def test_allocate_release_maintenance_utilisation(self):
        e = self.call("store", "post", "/api/equipment/", {"code": "mx-01", "name": "Concrete mixer", "ownership": "hired",
                                                           "hire_rate": "1500", "service_every_days": 30}, 201)
        url = f"/api/equipment/{e['id']}/"
        start = (TODAY - timedelta(days=4)).isoformat()
        self.call("store", "post", url + "allocate/", {"site": self.other.pk}, 400)        # not the store keeper's site
        d = self.call("store", "post", url + "allocate/", {"site": self.site.pk, "project": self.tower.pk, "from_date": start})
        self.assertEqual((d["status"], d["site"]), ("in_use", self.site.pk))
        self.call("store", "post", url + "allocate/", {"site": self.site.pk}, 400)          # already in use
        self.call("store", "patch", url, {"status": "available"})                           # status is read-only
        self.assertEqual(self.call("store", "get", url)["status"], "in_use")
        d = self.call("store", "post", url + "maintenance/", {"date": TODAY, "kind": "breakdown", "description": "Gearbox",
                                                              "cost": "4500", "downtime_hours": "6"})
        self.assertEqual(d["status"], "breakdown")
        self.call("store", "post", url + "back-in-service/")
        u = self.call("store", "get", "/api/equipment/utilisation/", {"from": start, "to": TODAY.isoformat()})
        row = u["rows"][0]
        self.assertEqual((row["days_allocated"], row["downtime_hours"], row["hire_cost"]), (5, 6.0, 7500.0))
        self.call("store", "post", url + "release/", {"to_date": TODAY.isoformat()})
        self.assertEqual(self.call("store", "get", url)["status"], "available")
        self.call("accounts", "get", "/api/equipment/", expect=403)


class ReportsTests(ModulesBase):
    def test_sections_follow_role_and_export(self):
        qs = self.call("qs", "get", "/api/reports/summary/")
        self.assertIn("indents", qs["sections"])
        self.assertIn("expenses", qs["sections"])
        self.assertNotIn("labour", qs["sections"])            # QS can't see labour
        pm = self.call("pm", "get", "/api/reports/summary/", {"project": self.tower.pk})
        self.assertEqual([p["code"] for p in pm["projects"]], ["TA"])
        self.call("store", "get", "/api/reports/summary/", expect=403)
        self.call("store", "get", "/api/reports/export/", expect=403)      # no reports module
        r = self.c("qs").get("/api/reports/export/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.call("qs", "get", "/api/reports/summary/", {"from": "2026-02-01", "to": "2026-01-01"}, 400)

    def test_dashboard_counts(self):
        p = self.call("pm", "get", "/api/auth/pending/")
        for k in ("tasks_mine", "tasks_overdue", "dpr_to_approve", "observations_open"):
            self.assertIn(k, p)
        self.assertNotIn("bills_to_approve", p)                                   # Project Head doesn't approve bills
        self.assertIn("bills_to_approve", self.call("management", "get", "/api/auth/pending/"))
        self.assertNotIn("bills_to_approve", self.call("safety", "get", "/api/auth/pending/"))
        people = self.call("store", "get", "/api/people/", {"site": self.site.pk})
        self.assertNotIn("Far Supervisor", [x["name"] for x in people])


def rowsof(d):
    return d["results"] if isinstance(d, dict) else d
