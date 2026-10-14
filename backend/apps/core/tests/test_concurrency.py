"""Concurrency: the same action fired at the same moment from several sessions (real threads, real PostgreSQL
transactions). Row locks must let exactly one through where only one is allowed — no double payment, no stock
below zero, no duplicate numbers or marks."""
import threading
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.finance.models import Expense, ExpensePayment
from apps.indents.models import Indent
from apps.materials.models import Material, StockEntry
from apps.sites.models import Site
from apps.sitework.models import Attendance, Worker

PW = "Str0ng-pass-123"
TODAY = timezone.localdate()


def race(n, fn):
    """Run fn(i) in n threads released together; return the results."""
    barrier = threading.Barrier(n)
    out = [None] * n

    def run(i):
        try:
            barrier.wait()
            out[i] = fn(i)
        finally:
            connections.close_all()
    ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    return out


@skipUnlessDBFeature("has_select_for_update")
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class Concurrency(TransactionTestCase):
    def setUp(self):
        cache.clear()
        call_command("seed", verbosity=0)
        self.site = Site.objects.create(code="TIM", name="Tridasha Imperial")
        self.U = {}
        for n, key in enumerate(["engineer", "store", "management", "accounts", "supervisor", "pm"]):
            u = User.objects.create_user(f"98000000{n:02d}", PW, name=key, role=Role.objects.get(key=key))
            u.sites.add(self.site)
            self.U[key] = u

    def client(self, key):
        c = APIClient()
        c.force_authenticate(self.U[key])
        return c

    def test_two_payments_of_the_full_amount_at_once_only_one_succeeds(self):
        e = Expense.objects.create(site=self.site, date=TODAY, category="Fuel", description="d", payee="P",
                                   amount=Decimal("1000"), status="approved", approved_amount=Decimal("1000"),
                                   approved_by=self.U["management"], created_by=self.U["accounts"])
        codes = race(4, lambda i: self.client("accounts").post(f"/api/expenses/{e.pk}/pay/",
                                                                {"date": TODAY, "amount": "1000", "ref": f"UTR{i}"},
                                                                format="json").status_code)
        e.refresh_from_db()
        self.assertEqual(sorted(codes), [200, 400, 400, 400], codes)
        self.assertEqual((e.paid_total, e.status, ExpensePayment.objects.filter(expense=e).count()),
                         (Decimal("1000"), "paid", 1))

    def test_issuing_the_last_bags_twice_at_once_never_goes_negative(self):
        m = Material.objects.create(code="CEM", name="Cement", unit="bag")
        StockEntry.objects.create(site=self.site, material=m, kind="IN", qty=10, date=TODAY, by=self.U["store"])
        codes = race(5, lambda i: self.client("store").post("/api/stock/", {"site": self.site.pk, "material": m.pk, "kind": "OUT",
                                                                            "qty": 10, "source": "manual"},
                                                             format="json").status_code)
        self.assertEqual(sorted(codes), [201, 400, 400, 400, 400], codes)
        self.assertEqual(StockEntry.balance(self.site.pk, m.pk), 0)

    def test_indents_raised_at_the_same_moment_get_distinct_numbers(self):
        codes = race(6, lambda i: self.client("engineer").post("/api/indents/", {"site": self.site.pk, "item": f"Item {i}",
                                                                                 "qty": 1}, format="json").status_code)
        self.assertEqual(codes, [201] * 6, codes)
        nums = list(Indent.objects.values_list("number", flat=True))
        self.assertEqual(len(nums), len(set(nums)))

    def test_same_attendance_marked_twice_at_once_gives_one_mark(self):
        w = Worker.objects.create(site=self.site, name="W", daily_wage=500, created_by=self.U["supervisor"])
        codes = race(4, lambda i: self.client("supervisor").post("/api/attendance/mark/", {
            "site": self.site.pk, "date": TODAY, "entries": [{"worker": w.pk, "status": "present"}]},
            format="json").status_code)
        self.assertTrue(all(c == 201 for c in codes), codes)              # later ones just re-mark the same day
        self.assertEqual(Attendance.objects.filter(worker=w, date=TODAY).count(), 1)

    def test_one_indent_approved_twice_at_once_moves_one_step(self):
        d = self.client("engineer").post("/api/indents/", {"site": self.site.pk, "item": "Sand", "qty": 1}, format="json").json()
        codes = race(3, lambda i: self.client("store").post(f"/api/indents/{d['id']}/act/", {"action": "approve"},
                                                             format="json").status_code)
        self.assertEqual(sorted(codes), [200, 400, 400], codes)
        i = Indent.objects.get(pk=d["id"])
        self.assertEqual((i.stage, i.history.filter(action="approve").count()), ("tech", 1))
