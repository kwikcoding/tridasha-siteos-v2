# Codex task — add "04a Quantity & budget check (QS)" before Management approval

**Repo:** `kwikcoding/tridasha-siteos-v2`. Django 5.2 + DRF backend in `backend/`, React + TypeScript (Vite) in `frontend/`, Playwright browser tests in `e2e/`.

**Base branch:** `verify-phase-3` (PR #9), or `main` once PR #9 is merged. It contains the self-approval rules this task extends.

**Create branch:** `qs-check`. Open a PR into the base branch. Do **not** merge it, deploy anything, or touch the live v1 site.

## Business decision (from the owner)

The indent flow becomes: 01 Raise → 02 Stock & open orders (Store Keeper) → 03 Technical (Project Head) → **04a Quantity & budget check (QS)** → **04b Requirement & budget approval (Management)** → stock available? → 05 … (unchanged after this point).

The Quantity Surveyor is the project's cost and contract controller. At 04a the QS checks the request against the BOQ / take-off and the budget, then forwards it to Management. Management still gives the approval at 04b, with the QS's figures in front of them.

## What to build

### 1. Workflow engine (`backend/apps/indents/workflow.py`, pure Python)

**New stage.** Add a new `Stage` immediately before `mgmt`:
- `n="04a"`, `key="qs"`, lane `"indent"`
- label "Check quantity & budget against BOQ", short "QS check", dept "QS / Quantity Surveyor"
- actions `("approve", "reject", "sendback", "hold")`
- `done="Under Verification"`, `approve_label="Quantity & budget checked — forward"`, `can_qty=True` (the QS may reduce the quantity), `required=False` (can be switched off in Settings)

**Renumber `mgmt`.** Change `mgmt` to `n="04b"`, label "Approve requirement & budget". The value limit (`mgmt_limit` / `mgmt_never` in `stage_on`) stays on `mgmt` only. The QS check happens for every indent while the step is on, whatever its value.

**Add `"qs"` to:**
- `BEFORE_PO`
- `SELF_APPROVAL_BLOCKED`: a QS who raised an indent can't check their own. The admin can, only as a recorded override with a reason, which works through the existing `is_override` logic.
- the key set in `prev_stage`, so "send back to previous step" from 04b returns to 04a, and from 04a to 03

**Roles.** In `DEFAULT_ROLE_STAGES`, set `"qs": ["qs"]`. Management keeps `["mgmt", "vendor", "payauth"]`.

**QS fields.** Add to `STAGE_FIELDS["qs"]`:
- `boq_ref`: moved here from `mgmt`. Management keeps `budget_note`.
- `boq_qty`: BOQ / take-off quantity for this item and location
- `qty_indented_to_date`: quantity already indented against this BOQ line, before this indent
- `budget_remaining`: ₹ left in the budget head
- `qs_note`: text

Add them to `FIELD_ORDER` after `spec_note`.

**Validation in `check_inputs`.** For `approve` at `qs`:
- Require `boq_ref`, or a remark saying why there is none (for example, a non-BOQ item).
- If `boq_qty` is given and `qty_indented_to_date + need(i)` exceeds `boq_qty`, require a remark ("Quantity exceeds BOQ by X — explain in Remarks").
- If `budget_remaining` is given and the indent value (`indent_value`) exceeds it, require a remark.
- Numbers can't be negative.

**Docs.** Update the module docstring's flow diagram and `ACTION_LABEL` / `BUTTON_LABEL` if needed.

### 2. Model and migrations (additive only)

**Fields.** Add to `Indent` (`backend/apps/indents/models.py`), all nullable:
- `boq_qty` (Decimal 14,3)
- `qty_indented_to_date` (Decimal 14,3)
- `budget_remaining` (Decimal 14,2)
- `qs_note` (TextField, blank=True)

**Schema migration.** Generate it with `makemigrations`. No field is removed or altered.

**Data migration.** In `backend/apps/accounts/migrations/`, modelled on `0003_fill_permissions`:
- Add `"qs"` to the stages of the built-in `qs` role.
- Make sure that role has `indents.view`. Acting at a step needs the step, not `indents.edit`, but check `allowed_actions` and the `act` endpoint permission (`module_permission("indents", act="indents.view")`).
- Don't change other roles. Make it reversible: the reverse removes `"qs"` from the stages.

**Also update** `backend/apps/accounts/roles.py`. The QS role description gains: "Step 04a — checks quantity against BOQ and budget before Management approval."

**Existing indents** already at `mgmt` stay there. Only indents that leave 03 after the change go to 04a. Add a test for this.

### 3. API and serializers

- `ActionDataSerializer` (`backend/apps/indents/services.py`) picks up the new fields through `STAGE_FIELDS`. Confirm negative values are refused in `validate`.
- `IndentDetailSerializer` (fields `__all__`) exposes them. Add the QS fields to the Excel export columns in `IndentViewSet.export`.
- Workflow meta (`/api/workflow/`) lists the new stage automatically. Check the Settings screen shows it with an on/off switch.
- Notifications (`backend/apps/alerts/tasks.py`): people at the `qs` stage for that site get the "Indent waiting for you" alert, through the existing `_people_at`. No change should be needed. Verify with a test.

### 4. Frontend

- `frontend/src/pages/IndentDetail.tsx`:
  - Add `FIELD_META` entries: "BOQ quantity", "Already indented against this BOQ line", "Budget remaining (₹)", "QS note".
  - In the QS action form, show a small panel like the existing `MoneyPanel`: requested quantity, BOQ quantity, already indented, **balance after this indent** (BOQ − already indented − this request, red if negative), and indent value against budget remaining.
- In the indent detail fields grid, show BOQ ref, BOQ qty and budget remaining once filled.
- The tracker shows 04a and 04b automatically from `steps`. Check the labels.
- Settings → Workflow: the new step appears with its switch. Relabel the limit section "Step 04b — management approval limit".
- `frontend/src/types.ts`: add the new fields.

### 5. Demo data (`backend/apps/accounts/management/commands/seed_demo.py`)

- `to_rfq` and every walk that passes 04 must add `("qs", "approve", {"data": {"boq_ref": "BOQ-TA-03.2", "boq_qty": …, "qty_indented_to_date": …, "budget_remaining": …}})` before `("management", "approve")`.
- Add one demo indent left waiting at 04a: "[DEMO] … waiting at 04a QS check (QS)".
- The command stays idempotent.

### 6. Tests (all must pass)

**Engine** (`backend/apps/indents/tests/test_workflow.py`):
- Full flow with QS: 02 → 03 → 04a (QS reduces the quantity) → 04b → … → 12b.
- QS step switched off goes 03 → 04b.
- QS over BOQ without a remark is refused; with a remark it passes.
- Over budget without a remark is refused.
- QS can't check their own indent.
- Admin at 04a is an override and needs a reason.
- Send back from 04b returns to 04a.
- Management can't act at 04a; QS can't act at 04b.
- An indent already at `mgmt` before the change still works.

**API** (`backend/apps/indents/tests/test_api.py`, `backend/apps/accounts/tests/test_access.py`, `test_cross_dept.py`, `test_roles_e2e.py`):
- Update every flow that walks past 03 to include the QS step.
- QS-role login acts at 04a and nowhere else.
- The QS gets the in-app notification when an indent reaches 04a at their site, but not for another site.
- Fields are saved and exported.

**Migrations:**
- `python manage.py makemigrations --check` is clean.
- The data migration adds `"qs"` to the QS role, and the reverse works.

**Browser** (`e2e/`):
- In `test_ui_roles.py` / `test_modules_ui.py`, a demo indent waiting at 04a is opened by the demo QS (mobile 9000000008). They fill BOQ fields, see the balance panel, and forward it.
- Management then sees it at 04b.
- A demo Store Keeper has no QS button.
- Update any existing flow that now passes through 04a.

**Other test files** that list stages and may need the new key:
- `backend/apps/legacy/tests/test_import.py` (stage list around line 128)
- `backend/apps/core/tests/test_performance.py` (stage list)
- `backend/apps/materials/tests/test_api.py` (walks through approvals)

CI (`.github/workflows/ci.yml`) runs everything: backend, frontend type-check and build, e2e, security, demo-stack, migrations-upgrade and backup-restore. All seven jobs must be green before you report done.

### 7. Docs

- `README.md`: in the indent flow description, add 04a.
- `VERIFICATION.md`: add a short "QS check (04a)" entry with the test evidence.

## Rules

- Keep existing behaviour otherwise unchanged. The purchase lane, money controls (steps 11–12), stock postings and the other modules are untouched.
- Migrations are additive and reversible. No reset of any database. Demo data only through `seed_demo`.
- Plain-language error messages, in the same style as the existing ones in `workflow.py`.
- No secrets in code or tests. Test passwords come from the existing test constants and CI variables.
- Do not deploy or merge. Report: files changed, test counts per CI job, and anything you could not do.
