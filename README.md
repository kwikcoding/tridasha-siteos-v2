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

Next phases: take-off, DPR, labour, expenses, dashboard, then data migration from v1.

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

GitHub Actions runs both, plus a frontend type-check and build, on every push.

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
