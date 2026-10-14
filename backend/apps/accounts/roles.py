"""Built-in roles (seeded into the Role table by `manage.py seed`). The admin can edit them or add new ones."""
from apps.indents.workflow import DEFAULT_ROLE_STAGES, DEFAULT_STEP_ACTIONS, STAGE

from .perms import ALL_CODES, from_view_edit

WORK_MODULES = ["dashboard", "reports", "sites", "tasks", "dpr", "labour", "materials", "indents",
                "equipment", "expenses", "quality", "docs"]
ADMIN_MODULES = ["team", "settings"]
STAGE_KEYS = list(STAGE.keys())

BUILTIN_ROLES = {
    "admin": dict(label="Administrator", color="gold", view=WORK_MODULES + ADMIN_MODULES, edit=WORK_MODULES + ADMIN_MODULES,
                  can_approve=True, all_sites=True,
                  description="Full control: staff, roles, workflow and rates. Can act at any step."),
    "pm": dict(label="Project Head", color="navy", view=WORK_MODULES, edit=WORK_MODULES, can_approve=True, all_sites=True,
               description="Step 03 — verifies the technical requirement (specification, quantity, actual site need)."),
    "qs": dict(label="QS / Quantity Surveyor", color="indigo",
               view=["dashboard", "reports", "sites", "materials", "indents", "expenses"], edit=[], all_sites=True,
               description="Step 04a — checks quantity against BOQ and budget before Management approval."),
    "engineer": dict(label="Site Engineer", color="violet",
                     view=["dashboard", "reports", "sites", "tasks", "dpr", "labour", "materials", "indents", "equipment", "quality", "docs"],
                     edit=["tasks", "dpr", "labour", "materials", "indents", "equipment", "quality", "docs"],
                     description="Step 01 — raises indents. Step 09 — inspects deliveries with Stores; confirms issue at step 10."),
    "purchase": dict(label="Purchase", color="orange", view=["dashboard", "reports", "sites", "materials", "indents", "expenses"],
                     edit=["indents"], all_sites=True,
                     description="Steps 05, 07, 08 — quotations, purchase order, delivery tracking; step 11 with Accounts."),
    "management": dict(label="Management / Authorised Approver", color="red", view=WORK_MODULES, edit=["indents"],
                       can_approve=True, all_sites=True,
                       description="Step 04b — approves requirement & budget; step 06 — approves the supplier; step 12 — authorises payment."),
    "supervisor": dict(label="Site Supervisor", color="teal",
                       view=["dashboard", "tasks", "dpr", "labour", "materials", "indents", "equipment", "quality"],
                       edit=["dpr", "labour", "indents", "quality"],
                       description="Daily reports, attendance, raises indents, site observations."),
    "store": dict(label="Store Keeper", color="green", view=["dashboard", "materials", "indents", "equipment", "dpr"],
                  edit=["materials", "indents", "equipment"],
                  description="Step 02 — stock & open orders; issues from stock; step 09 — receives; step 10 — issues and closes."),
    "accounts": dict(label="Accountant", color="pink",
                     view=["dashboard", "reports", "sites", "expenses", "labour", "materials", "indents"], edit=["expenses", "indents"],
                     description="Step 11 — invoice vs PO vs GRN; step 12 — settles payment."),
    "safety": dict(label="Safety Officer", color="red", view=["dashboard", "quality", "dpr", "labour", "docs"], edit=["quality"],
                   description="Safety observations, incidents and NCR closure."),
    "viewer": dict(label="Viewer (read-only)", color="slate", view=WORK_MODULES, edit=[],
                   description="Can see everything on assigned sites, changes nothing."),
}
# extra permission codes beyond the plain view/edit translation
EXTRA_CODES = {
    "store": ["materials.import", "materials.stock", "indents.export"],
    "accounts": ["expenses.approve", "reports.export"],
    "management": ["expenses.approve", "dpr.approve", "reports.export", "dashboard.export"],
    "pm": ["dpr.approve", "labour.approve", "quality.approve", "tasks.assign"],
    "safety": ["quality.approve"],
    "qs": ["reports.export"],
}
for key, r in BUILTIN_ROLES.items():
    r["stages"] = list(DEFAULT_ROLE_STAGES.get(key, []))
    r["step_actions"] = dict(DEFAULT_STEP_ACTIONS.get(key, {}))
    if key == "admin":
        r["permissions"] = list(ALL_CODES)
    else:
        r["permissions"] = sorted(set(from_view_edit(r["view"], r["edit"])) | set(EXTRA_CODES.get(key, [])))
