# Tridasha SiteOS v2

The construction ERP for Tridasha Imperial, rebuilt as:

| Part | Tech |
|---|---|
| `frontend/` | React 18 + TypeScript, Vite, Tailwind, React Router, TanStack Query |
| `backend/` | Django 5 + Django REST Framework, PostgreSQL 16 |
| Alerts & scheduled checks | Celery + Redis (WhatsApp Cloud API, email, SMS via MSG91) — no n8n |
| Data in / out | Excel/CSV uploads and Excel downloads — no live Google Sheets |

## Phase 1 (this commit)

- **Mobile + password login** (secure session cookie, CSRF, login rate limit).
- **Admin-managed roles and one login per person** — built-in roles plus custom roles; each role picks the workflow steps it acts on, the modules it can see/change, and whether it works on all sites.
- **The 12-step indent & purchase workflow** (`backend/apps/indents/workflow.py`), enforced on the server:
  `01 raise → 02 stock → 03 technical → 04 requirement & budget → stock available? → 05 quotations → 06 supplier → 07 PO → 08 delivery (+09 receive) → 10 issue & close`, then the purchase lane `11 invoice → 12 payment`.
  Status only changes through `POST /api/indents/{id}/act/`; every action is written to an append-only history.
- **Alerts**: "indent waiting for you", "sent back / rejected / complete", "delivery overdue" (every 3 h), daily "waiting more than a day" digest. In-app bell always; WhatsApp / email / SMS when configured.
- **Excel download** of indents.
- Sites, Team & roles admin screens.

## Phase 2

- **Materials → Catalogue**: items the stores keep (code, name, category, unit, rate, GST, HSN, reorder level). Upload .xlsx/.csv — the app shows what will be added/updated and any bad lines before you confirm. Matched by code; blank cells never wipe data.
- **Materials → Materials register**: the High-Rise Construction Materials Master. Upload its "Materials Register" tab as is (title rows are skipped). Filter by trade / applicability / status, edit rows, link a row to a catalogue item, download Excel.
- **Materials → Stock**: per-site balances and the full ledger. Entries are never edited or deleted — corrections are adjustments with a reason. Stock can't go below zero.
- **Indents ↔ stock**: pick a catalogue item when raising an indent. Store sees the site balance at the stock check; *issue from stock* posts OUT (and is blocked if stock is short), *receive* posts IN with the GRN, *issue & close* posts OUT to site.

## Phase 3 — access control

- **Team & Roles** (admin): People (employee ID, designation, department, reporting manager, main + extra roles, sites, alerts, reset password), Roles (workflow steps and, per step, which actions), **Permission matrix** (roles × module permissions: view / create / edit / approve / export / upload / post stock …), Departments, Sites, **Audit log**.
- Permissions are checked by Django on every request; the menu only hides what the server would refuse anyway.
- New logins and admin password resets use a temporary password — the person must set their own at first sign-in.
- **Step 12 is split**: 12a *Authorise payment* (Management) → 12b *Settle payment* (Accountant). Whoever authorised a payment can't also settle it — administrator included.
- **Step 11**: only the Accountant verifies the invoice; Purchase can hold or return it. **Step 10**: Store Keeper or Site Engineer can issue & close.
- **Administrator overrides**: the admin can act at any step, but must give a reason; it's flagged in the indent history and in the audit log.
- Audit log covers sign-ins (and failed attempts), logins created/changed, password resets, role and permission changes, overrides, stock entries, uploads and workflow settings.
- Sidebar, Dashboard (pending approvals and counts), Profile (change password), Access denied, Settings (workflow steps & management limit).

## Verification pass (October 2026)

- **Step 11 — three-way match**: the invoice (before GST) is compared with PO rate × quantity received on GRNs. A difference beyond the tolerance (default 1 %, *Settings → Workflow*) needs a written reason, which is kept in the history.
- **Step 12a** records the **amount authorised** — never more than the verified invoice incl. GST.
- **Step 12b** records each payment with its amount. Part payments are allowed (*Part Paid*); the total can't exceed the authorised amount; the same payment reference can't be recorded twice on an indent. The purchase closes when the authorised amount is fully paid.
- **Step 09** refuses receiving more than is still on order.
- No new indents on a closed site. Dashboard "Raised by you" counts every open indent (it used to stop at 50).
- **Fixed sign-in bounce** in the production build (the app could return to the login page after a successful sign-in).
- Full results: [VERIFICATION.md](VERIFICATION.md).

## All modules (October 2026)

Sites & Projects, Tasks & Schedule, Daily Progress, Labour & Attendance, Plant & Equipment, Expenses & Bills,
Quality & Safety, Drawings & Documents and Reports are built, each with site isolation, server-side permissions,
audit log, Excel export and attachments. Uploaded files are kept under `backend/media/` (not in git) and are
downloaded only through the API. See [VERIFICATION.md](VERIFICATION.md) for what each module enforces and the test results.

## Demo stack (separate database)

Try everything on realistic data without touching your working database:

```bash
DEMO_PASSWORD=choose-one docker compose --profile demo up -d --build
```

- App: http://localhost:5174 (API on :8001). It has its own Postgres container and volume (`siteos_demo`) and its own uploads folder (`backend/media-demo`).
- Demo logins: mobiles 9000000001–9000000010, one per role, all with the password you chose. The admin login is the same one set in `.env`.
- It holds two demo projects, plus tasks, daily reports, muster roll and attendance, bills at every stage, quality and safety items, drawings with revisions, equipment, and indents waiting at every step.
- Stop it with `docker compose --profile demo down`. Add `-v` to drop the demo database too.
- The normal `docker compose up` doesn't start any of this.

**Settings → Company profile** (admin) holds the company name, GSTIN, PAN, address and logo. These appear in the header and on report exports.

Next: v1 data import, production setup.

## Run it locally (Docker — easiest)

```bash
cp .env.example .env          # set ADMIN_MOBILE and ADMIN_PASSWORD for your first login
docker compose up --build
```

- App: http://localhost:5173  — sign in with ADMIN_MOBILE / ADMIN_PASSWORD
- API docs: http://localhost:8000/api/docs/
- Then: Team & roles → add a site → add people (one login each, with a role).

## Run without Docker

```bash
# backend (needs Postgres and Redis running)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DJANGO_DEBUG=1 DATABASE_URL=postgres://siteos:siteos@localhost:5432/siteos
python manage.py migrate && ADMIN_MOBILE=98xxxxxxxx ADMIN_PASSWORD='choose-one' python manage.py seed
python manage.py runserver
celery -A config worker -l info      # second terminal (alerts)
celery -A config beat -l info        # third terminal (scheduled checks)

# frontend
cd frontend && npm install && npm run dev
```

## Tests

```bash
cd backend
python -m unittest apps.indents.tests.test_workflow     # workflow engine, no database
python manage.py test apps                              # API tests (needs Postgres)
```

GitHub Actions runs both, plus a frontend type-check and build, on every push — and **browser tests**
(`e2e/`, Playwright + Chromium): every role signs in through the login form against the production build, the
sidebar and direct-URL restrictions are checked, an indent is raised and stock-checked in the browser, and the main
pages are checked at phone width. Test logins exist only in the throw-away CI database.

## VS Code

Open the repo folder. Accept the recommended extensions (Python, Pylance, Ruff, ESLint, Tailwind, Docker).
Create `backend/.venv` as above so VS Code picks the interpreter automatically.

## Changing the database models

After editing a `models.py`, run `python manage.py makemigrations` and commit the new file.
No local Python? Run **Actions → Make migrations → Run workflow** and download the files from the run.

## Layout

```
backend/
  config/            settings, urls, celery
  apps/accounts/     User (mobile login), Role, auth + team APIs, `manage.py seed`
  apps/sites/        Site
  apps/indents/      workflow.py (12 steps), models, services (the only writer), API, tests
  apps/materials/    catalogue, register, stock ledger, importer.py (xlsx/csv), services
  apps/alerts/       Notification, channels (WhatsApp/email/SMS), Celery tasks
frontend/src/
  pages/             Login, Indents, IndentDetail (tracker + actions), NewIndent, Materials, Team
  api.ts auth.tsx    fetch wrapper (CSRF), session/me
```
