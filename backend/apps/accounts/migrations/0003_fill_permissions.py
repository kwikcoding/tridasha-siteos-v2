"""Give every existing role its permission codes and the step-12 split. Additive only:
no user, role assignment, indent or history row is deleted or renumbered."""
from django.db import migrations

# frozen copies of the defaults at the time of this migration
EXTRA = {
    "store": ["materials.import", "materials.stock", "indents.export"],
    "accounts": ["expenses.approve", "reports.export"],
    "management": ["expenses.approve", "dpr.approve", "reports.export", "dashboard.export"],
    "pm": ["dpr.approve", "labour.approve", "quality.approve", "tasks.assign"],
    "safety": ["quality.approve"],
    "qs": ["reports.export"],
}
VERBS = {
    "dashboard": ["view", "export"], "reports": ["view", "export"], "sites": ["view", "create", "edit", "export"],
    "tasks": ["view", "create", "edit", "assign", "delete", "export"], "dpr": ["view", "create", "edit", "approve", "export"],
    "labour": ["view", "create", "edit", "approve", "export"],
    "materials": ["view", "create", "edit", "import", "stock", "export"], "indents": ["view", "create", "edit", "cancel", "export"],
    "equipment": ["view", "create", "edit", "export"], "expenses": ["view", "create", "edit", "approve", "export"],
    "quality": ["view", "create", "edit", "approve", "export"], "docs": ["view", "create", "edit", "delete", "export"],
    "team": ["view", "manage", "audit"], "settings": ["view", "manage"],
}
ADMIN_ONLY = {"team.manage", "settings.manage", "team.audit"}


def codes_from(view, edit):
    out = set()
    for m in view or []:
        if m in VERBS:
            out.add(f"{m}.view")
            if "export" in VERBS[m]:
                out.add(f"{m}.export")
    for m in edit or []:
        if m in VERBS:
            out |= {f"{m}.{v}" for v in ("create", "edit") if v in VERBS[m]}
            if m == "indents":
                out.add("indents.cancel")
    return out


def forwards(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    all_codes = [f"{m}.{v}" for m, vs in VERBS.items() for v in vs]
    for r in Role.objects.all():
        if r.key == "admin":
            r.permissions = all_codes
        elif not r.permissions:
            codes = codes_from(r.view, r.edit) | set(EXTRA.get(r.key, [])) if r.builtin else codes_from(r.view, r.edit)
            if r.builtin and r.key == "qs":       # QS is read-only by default
                codes -= {"indents.create", "indents.edit", "indents.cancel"}
            if r.stages:
                codes.add("indents.view")
            r.permissions = sorted(c for c in codes if c not in ADMIN_ONLY)
        stages = list(r.stages or [])
        if r.builtin and r.key == "management" and "payment" in stages:
            stages = [("payauth" if s == "payment" else s) for s in stages]       # 12a authorise
        if r.builtin and r.key == "engineer" and "issue" not in stages:
            stages.append("issue")                                                # may close at step 10
        if r.builtin and r.key == "purchase" and "invoice" in stages and not r.step_actions:
            r.step_actions = {"invoice": ["holdInv", "returnInv"]}                 # Accountant verifies
        r.stages = stages
        r.save()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_role_permissions_role_step_actions_user_designation_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
