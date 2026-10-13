"""Every built-in role signs in for real (session login, no force_authenticate) and probes each module's API.

Expected access comes from the documented role table in apps/accounts/roles.py — the test proves the server
enforces it, independently of what the React menu shows. Direct calls to forbidden endpoints must get 403.
"""
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.roles import BUILTIN_ROLES
from apps.materials.models import Material
from apps.sites.models import Site

PW = "Str0ng-pass-123"
ROLES = ["admin", "management", "pm", "purchase", "accounts", "qs", "safety", "engineer", "supervisor", "store"]


def expected_codes(key):
    return set(BUILTIN_ROLES[key]["permissions"])


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class RoleSignInMatrix(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)
        cls.site = Site.objects.create(code="TIM", name="Tridasha Imperial")
        cls.cement = Material.objects.create(code="CEM", name="Cement", unit="bag")
        cls.U = {}
        for n, key in enumerate(ROLES):
            if key == "admin":
                u = User.objects.create_superuser(f"94000000{n:02d}", PW, name="Admin")
            else:
                u = User.objects.create_user(f"94000000{n:02d}", PW, name=key, role=Role.objects.get(key=key))
            u.sites.add(cls.site)
            cls.U[key] = u

    def setUp(self):
        cache.clear()

    def login(self, key):
        c = APIClient()
        r = c.post("/api/auth/login/", {"mobile": self.U[key].mobile, "password": PW}, format="json")
        self.assertEqual(r.status_code, 200, (key, r.content))
        return c

    def probes(self):
        """(label, method, url, body, permission(s) that allow it; None = admin only, "*" = everyone signed in)"""
        s, m = self.site.pk, self.cement.pk
        return [
            ("indents list", "get", "/api/indents/", None, "indents.view"),
            ("indents export", "get", "/api/indents/export/", None, "indents.export"),
            ("raise indent", "post", "/api/indents/", {"site": s, "item": "Cement", "unit": "bag", "qty": 1}, "indents.create"),
            ("materials", "get", "/api/materials/", None, ("materials.view", "indents.create")),   # raisers search it
            ("register", "get", "/api/register/", None, "materials.view"),
            ("stock ledger", "get", "/api/stock/", None, "materials.view"),
            ("post stock", "post", "/api/stock/", {"site": s, "material": m, "kind": "IN", "qty": 5, "source": "manual"},
             "materials.stock"),
            ("add material", "post", "/api/materials/", {"code": "X-1", "name": "X", "unit": "nos"}, "materials.create"),
            ("staff list", "get", "/api/users/", None, "team.view"),
            ("roles list", "get", "/api/roles/", None, "*"),             # labels for chips; editing is admin-only
            ("create role", "post", "/api/roles/", {"key": "x", "label": "X"}, None),
            ("audit log", "get", "/api/audit/", None, None),
            ("workflow settings", "put", "/api/workflow/settings/", {"stages": {}, "mgmt_limit": 0}, None),
            ("v1 archive", "get", "/api/legacy/records/", None, None),
            ("create site", "post", "/api/sites/", {"code": "NEW", "name": "New"}, None),
        ]

    def test_each_role_signs_in_and_api_enforces_its_permissions(self):
        failures = []
        for key in ROLES:
            c = self.login(key)
            me = c.get("/api/auth/me/").json()
            if key == "admin":
                self.assertTrue(me["is_admin"])
            else:
                self.assertFalse(me["is_admin"], key)
                self.assertEqual(set(me["permissions"]), expected_codes(key), key)
                self.assertEqual(sorted(me["stages"]), sorted(BUILTIN_ROLES[key]["stages"]), key)
            self.assertEqual(c.get("/api/auth/pending/").status_code, 200)
            for label, method, url, body, code in self.probes():
                codes = (code,) if isinstance(code, str) else (code or ())
                allowed = key == "admin" or code == "*" or any(c_ in expected_codes(key) for c_ in codes)
                r = getattr(c, method)(url, body, format="json") if body is not None else getattr(c, method)(url)
                ok = (r.status_code in (200, 201)) if allowed else (r.status_code == 403)
                if not ok:
                    failures.append(f"{key}: {label} → {r.status_code} (expected {'allowed' if allowed else '403'})")
            c.post("/api/auth/logout/")
            self.assertEqual(c.get("/api/auth/me/").status_code, 403, f"{key} still signed in after logout")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_signed_out_gets_nothing(self):
        c = APIClient()
        for _, method, url, body, _ in self.probes():
            self.assertEqual(getattr(c, method)(url, body or {}, format="json").status_code, 403, url)

    def test_deactivated_account_cannot_sign_in_and_session_ends(self):
        c = self.login("store")
        u = self.U["store"]
        u.is_active = False
        u.save()
        self.assertEqual(c.get("/api/indents/").status_code, 403)
        r = APIClient().post("/api/auth/login/", {"mobile": u.mobile, "password": PW}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_qs_is_read_only_and_safety_cannot_see_indents(self):
        qs = self.login("qs")
        self.assertEqual(qs.get("/api/indents/").status_code, 200)
        self.assertEqual(qs.post("/api/indents/", {"site": self.site.pk, "item": "C", "qty": 1}, format="json").status_code, 403)
        safety = self.login("safety")
        self.assertEqual(safety.get("/api/indents/").status_code, 403)
        self.assertEqual(safety.get("/api/materials/").status_code, 403)
