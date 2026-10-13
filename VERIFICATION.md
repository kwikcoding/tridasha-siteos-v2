# Tridasha SiteOS v2 — functional & business-logic verification

**Date:** 13 Oct 2026 · **Branch:** `verify-p0-finance` (PR #6) · **Environment:** GitHub Actions on PostgreSQL 16 (throw-away CI databases). Nothing was run against the live v1 site or the laptop database.

## What was run

All results below come from CI runs on this branch. The last run passed all three jobs.

| Suite | Where | Tests | Result |
|---|---|---|---|
| Workflow engine and Excel parser (no database) | `backend/apps/indents/tests/test_workflow.py`, `apps/materials/tests/test_importer.py` | 32 | passed |
| API, permissions and database (session auth, PostgreSQL) | `manage.py test apps` (8 files) | 84 in total, including the 32 above | passed |
| Every role signs in for real; each module API probed for allowed / 403 | `apps/accounts/tests/test_roles_e2e.py` | 4 (10 roles × 14 endpoints) | passed |
| Browser (Playwright/Chromium against the production build) | `e2e/test_ui_roles.py` | 12 | passed |
| Frontend type-check and production build | `npm run typecheck && npm run build` | — | passed |
| Migrations match the models | `makemigrations --check` | — | passed |

**Not run:**
- React component unit tests: none exist yet. The browser tests cover the screens instead.
- WhatsApp, SMS and email delivery: no provider credentials. In-app notifications are tested.
- Load and query-performance tests.
- A manual click-through on the laptop since these fixes.

## Issues found and fixed

| # | Issue | Root cause | Fix | Regression test |
|---|---|---|---|---|
| 1 | Step 11 had no invoice vs PO × GRN check | not implemented | The invoice (before GST) is matched against PO rate × received quantity. Beyond the tolerance it needs a written reason. The tolerance is an admin setting and is audited. | `MoneyControls.*`, `test_invoice_mismatch_*`, `test_tolerance_setting_*` |
| 2 | Step 12a recorded no amount | not implemented | The authorised amount is required and capped at the invoice incl. GST | `test_authorise_*` |
| 3 | Step 12b allowed any amount, and only one payment | not implemented | The amount is required. Part payments are allowed. The total can't exceed the amount authorised. A duplicate payment reference is refused. The purchase closes when fully paid. | `test_part_payments_*`, `test_excess_payment_refused` |
| 4 | Step 09 could receive more than ordered | no cap in `transition("receive")` | Refused, with the quantity still to receive shown | `Receipts.test_cannot_receive_more_than_ordered` |
| 5 | Sign-in could bounce back to the login page (production build) | `queryClient.clear()` detached the watched `me` query | Update `me` in place and drop the other cached data | the browser tests, which failed before the fix and pass after |
| 6 | Dashboard "Raised by you (open)" stopped counting at 50 | counted the first API page only | Server-side count (`raised_open`) | `test_raised_open_counts_beyond_first_page` |
| 7 | Indents could be raised on a closed site | `active` flag not checked | Refused | `test_no_new_indent_on_closed_site_*` |
| 8 | Two simultaneous indents could get the same number (an error, not bad data) | count-based numbering | Retry with the next number | covered by the creation tests (the race itself isn't simulated) |
| 9 | "Payment Authorised" chip had no colour | missing tone | Added, plus "Part Paid" | visual |
| 10 | Django's request log was silenced | logging config disabled existing loggers | `disable_existing_loggers: False` | visible in the CI logs |

Database change: `indents/0004_money_controls` is additive only. It adds three nullable money columns and one setting with a default. Nothing is dropped or rewritten.

## Final verification table

| Module | UI | Functions | Business Logic | API | Database | Permissions | Final Status |
|---|---|---|---|---|---|---|---|
| Dashboard | PARTIALLY WORKING — 4 KPI cards and the approvals queue. No project summary, filters or date ranges. | PARTIALLY WORKING | VERIFIED WORKING — counts tested against the database | VERIFIED WORKING | VERIFIED WORKING | VERIFIED WORKING — cards follow role (browser test) | **PARTIALLY WORKING** |
| Reports | NOT IMPLEMENTED | NOT IMPLEMENTED — only Excel exports of indents, stock and register | NOT IMPLEMENTED | NOT IMPLEMENTED | — | permission codes only | **NOT IMPLEMENTED** |
| Sites & Projects | PARTIALLY WORKING — sites under Team & Roles → Sites. No Projects page. | PARTIALLY WORKING — create / edit / close a site | VERIFIED WORKING — site isolation; closed site blocks new indents | VERIFIED WORKING | VERIFIED WORKING | VERIFIED WORKING — admin-only edits | **PARTIALLY WORKING** (no Projects entity) |
| Tasks & Schedule | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | — | codes only | **NOT IMPLEMENTED** |
| Daily Progress | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | — | codes only | **NOT IMPLEMENTED** |
| Labour & Attendance | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | — | codes only | **NOT IMPLEMENTED** |
| Materials & Stock | VERIFIED WORKING — access per role in the browser | VERIFIED WORKING — catalogue, register, ledger, imports, exports | VERIFIED WORKING — no negative stock, row lock per material, ledger corrected by adjustments only | VERIFIED WORKING | VERIFIED WORKING | VERIFIED WORKING | **PARTIALLY WORKING** (units are free text; no project linkage because there is no Projects entity) |
| Indents & Purchase | VERIFIED WORKING — raise and stock check in the browser; steps 11–12 money panel | VERIFIED WORKING — steps 01–12, holds, send-backs, rejects, cancels, partial receipts | VERIFIED WORKING — now incl. three-way match, authorised amount, part payment, no excess or duplicate payments, no over-receipt | VERIFIED WORKING | VERIFIED WORKING — atomic actions with row locks; append-only history | VERIFIED WORKING — each role only at its own steps; separation of duties at step 12 | **VERIFIED WORKING** (one invoice per indent; external alert channels NOT TESTED) |
| Plant & Equipment | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | — | codes only | **NOT IMPLEMENTED** |
| Expenses & Bills | NOT IMPLEMENTED (procurement bills are handled at indent steps 11–12) | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | — | codes only | **NOT IMPLEMENTED** |
| Quality & Safety | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | — | codes only | **NOT IMPLEMENTED** |
| Drawings & Documents | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | NOT IMPLEMENTED | — | codes only | **NOT IMPLEMENTED** |
| Team & Roles | VERIFIED WORKING — admin-only page; direct URL refused for the other 9 roles | VERIFIED WORKING — staff, roles, matrix, departments, sites, audit | VERIFIED WORKING — multi-role, deactivation ends the session, forced password change, no self role change | VERIFIED WORKING | VERIFIED WORKING | VERIFIED WORKING — 10 roles × 14 endpoints | **VERIFIED WORKING** (department-based data scoping not built) |
| Settings | VERIFIED WORKING — workflow tab | PARTIALLY WORKING — workflow steps, step-04 limit, step-11 tolerance, v1 import, demo data. No company or project settings. | VERIFIED WORKING — changes apply from the next action; history unchanged | VERIFIED WORKING | VERIFIED WORKING — persisted in PostgreSQL | VERIFIED WORKING — admin-only, audited | **PARTIALLY WORKING** |

### Roles (all 10 signed in, via the API and in the browser)

Administrator, Management / Authorised Approver, Project Head, Purchase, Accountant, QS, Safety Officer, Site Engineer, Site Supervisor and Store Keeper. Each was checked for:
- sign-in and sign-out
- sidebar
- direct URLs to Team, Settings, Materials, Indents and New indent
- the API refusing anything outside the role (403)
- workflow steps, which only that role can act at (`test_each_role_only_at_its_steps`)

QS is read-only. Safety sees neither indents nor materials. Only the administrator reaches Team & Roles and Settings.

## Remaining issues (priority order)

1. **P1:** Projects entity, then project-wise data in materials and indents.
   - Department-based data scoping.
   - DPR, Labour & Attendance, and Expenses & Bills modules.
   - The v1 data import still needs the v1 Google Sheets uploaded.
2. **P2:**
   - Reports.
   - Tasks, Equipment, Quality & Safety, and Documents modules.
   - More than one invoice per indent.
   - A unit-of-measure master.
   - React component tests.
   - Testing the WhatsApp, SMS and email channels once credentials exist.
   - Speed of the queue view.
3. **Production setup:** not done. It needs approval and is not deployed automatically.
