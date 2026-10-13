"""The permission catalogue: every module, the actions on it, and how the sidebar groups them.

A permission code is "<module>.<verb>", e.g. "materials.import". Roles hold a list of codes;
a person's effective permissions are the union over all their roles. The administrator has all.
"""

MODULE_GROUPS = [
    ("Overview", [("dashboard", "Dashboard"), ("reports", "Reports")]),
    ("Site work", [("sites", "Sites & Projects"), ("tasks", "Tasks & Schedule"), ("dpr", "Daily Progress"),
                   ("labour", "Labour & Attendance")]),
    ("Resources", [("materials", "Materials & Stock"), ("indents", "Indents & Purchase"), ("equipment", "Plant & Equipment")]),
    ("Finance", [("expenses", "Expenses & Bills")]),
    ("Compliance", [("quality", "Quality & Safety"), ("docs", "Drawings & Documents")]),
    ("Administration", [("team", "Team & Roles"), ("settings", "Settings")]),
]
MODULE_LABEL = {k: label for _, mods in MODULE_GROUPS for k, label in mods}
MODULES = list(MODULE_LABEL)
WORK_MODULES = [m for m in MODULES if m not in ("team", "settings")]

VERB_LABEL = {
    "view": "View", "create": "Create", "edit": "Edit", "delete": "Delete", "export": "Export", "approve": "Approve",
    "assign": "Assign", "import": "Upload Excel", "stock": "Post stock", "cancel": "Cancel", "manage": "Manage",
    "audit": "View audit log",
}

# which verbs exist for each module
MODULE_VERBS = {
    "dashboard": ["view", "export"],
    "reports": ["view", "export"],
    "sites": ["view", "create", "edit", "export"],
    "tasks": ["view", "create", "edit", "assign", "delete", "export"],
    "dpr": ["view", "create", "edit", "approve", "export"],
    "labour": ["view", "create", "edit", "approve", "export"],
    "materials": ["view", "create", "edit", "import", "stock", "export"],
    "indents": ["view", "create", "edit", "cancel", "export"],
    "equipment": ["view", "create", "edit", "export"],
    "expenses": ["view", "create", "edit", "approve", "export"],
    "quality": ["view", "create", "edit", "approve", "export"],
    "docs": ["view", "create", "edit", "delete", "export"],
    "team": ["view", "manage", "audit"],
    "settings": ["view", "manage"],
}
ALL_CODES = [f"{m}.{v}" for m in MODULES for v in MODULE_VERBS[m]]
ADMIN_ONLY_CODES = {"team.manage", "settings.manage", "team.audit"}   # never grantable to a non-admin role


def catalogue():
    """For the permission-matrix screen."""
    return [{"group": g, "modules": [{"key": m, "label": label,
                                      "perms": [{"code": f"{m}.{v}", "verb": v, "label": VERB_LABEL[v],
                                                 "admin_only": f"{m}.{v}" in ADMIN_ONLY_CODES}
                                                for v in MODULE_VERBS[m]]} for m, label in mods]}
            for g, mods in MODULE_GROUPS]


def from_view_edit(view, edit):
    """Translate the older view/edit module lists into permission codes."""
    codes = set()
    for m in view or []:
        if m in MODULE_VERBS:
            codes.add(f"{m}.view")
            if "export" in MODULE_VERBS[m]:
                codes.add(f"{m}.export")
    for m in edit or []:
        if m not in MODULE_VERBS:
            continue
        for v in ("create", "edit"):
            if v in MODULE_VERBS[m]:
                codes.add(f"{m}.{v}")
        if m == "indents":
            codes.add("indents.cancel")
    return sorted(codes & set(ALL_CODES))


def clean_codes(codes):
    """Keep known, grantable codes; 'X.anything' implies 'X.view'."""
    out = {c for c in (codes or []) if c in ALL_CODES and c not in ADMIN_ONLY_CODES}
    out |= {c.split(".")[0] + ".view" for c in out}
    return sorted(out)


def view_edit_from_codes(codes):
    """Keep the legacy view/edit lists in step with the codes."""
    view = sorted({c.split(".")[0] for c in codes if c.endswith(".view")})
    edit = sorted({c.split(".")[0] for c in codes if c.split(".")[1] in ("create", "edit")})
    return view, edit
