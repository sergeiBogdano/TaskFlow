# TaskFlow Backend

FastAPI backend for TaskFlow Dashboard.

Main documentation is available in the root [README.md](../README.md).

## Includes

- FastAPI REST API
- SQLAlchemy async models and database access
- Alembic migrations
- APScheduler background jobs
- Role and permission logic
- Client, task, calendar, Kanban, report and notification APIs

## Development

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.web.app:app --host 0.0.0.0 --port 8080 --reload
```

## Users, workspaces and CRM

The first installation requires `BOOTSTRAP_USERNAME` (default `admin`) and a unique
`BOOTSTRAP_PASSWORD` of at least eight characters. The initial account is platform
root; its password is managed exclusively on the server. Bootstrap
credentials do not reset an existing installation. After updating an existing
installation, all users must sign in again because session tokens now include an
account version and expiry. Blocking an account or resetting its password revokes
existing sessions.

Root manages platform roles, feature switches and workspace modules. Platform
administrators can provision accounts and workspaces; they access workspace
contents through membership. Owners and administrators manage membership inside
their own workspace and delegate only their actual workspace permissions. They
cannot reset platform account passwords. Custom workspace roles specify an exact
set of capabilities, independently of the management rank. Restarting the server
never expands these permissions or invites unassigned users into a team.

Workspaces can be hidden, closed or open. Hidden workspaces appear only to members
and root; closed workspaces appear in the directory but require an invitation;
open workspaces allow signed-in users to join as members. Study and project presets
enable tasks and notes. Root can enable CRM, reporting, automation and AI separately
for each workspace. New catalogue entries are off by default. Disabling a module
preserves its data and pauses its automation. Restoring a disabled module retains
its workspace feature restrictions until root explicitly enables the relevant
functions. Restoring a globally disabled function likewise does not automatically
restore access for existing users: enable the user override explicitly.

CRM includes scoped contacts, organizations and contracts, multiple sales pipelines
with configurable stages and outcomes, deals, responsible users, activities and
custom fields (text, number, date and checkbox). Field order supports drag and
keyboard controls. Deals support archive, trash, restore and permanent removal;
contacts support trash and restore. Contract renewal validates the new end date,
preserves the contract identity and creates a linked task. Earlier renewal tasks
keep their `contract_id`. Deals can create multiple related tasks directly; task
history respects task visibility and includes renewals of their linked contract.
Deleting a deal preserves the work history and detaches its task references.
Contract files require the contracts capability, and file changes require client
editing rights. Archived deals remain visible when moved to trash. Linked contracts cannot be removed through an organization
edit; archive them or remove the links first. This implementation is a foundation
for CRM workflows, not full Bitrix24 feature parity: payment processing, invoices, external integrations and telephony are outside the
current scope. Sales stages and recurring task modules are configurable; a generic
business-process designer is not included.

Workspace appearance supports themes, labels, menu visibility and configurable task
and sprint fields. Task field ordering operates within existing form groups. Personal
browser notes use a stable account identifier; re-creating a deleted username does
not inherit its notes, feature overrides or old sessions; the former shared `taskflow-local-notes`
IndexedDB is retained and is not automatically attributed to an account.

### Root password maintenance

No user, including root itself, can change root's password through the web UI or
HTTP API. This restriction does not depend on role or feature switches. Initial
provisioning uses a unique `BOOTSTRAP_PASSWORD`; root is not forced into the ordinary
user password-change form. Updating that environment variable does not reset an
existing account.

On the server, from `taskflow-seo` with the deployment environment loaded, run:

```bash
python -m app.cli root-password
```

For Docker:

```bash
docker compose exec web python -m app.cli root-password
```

The command asks for the new password twice without displaying it. Passwords are
not accepted in command arguments or a pipe. It updates the salted password hash
in the configured database, clears any obsolete onboarding flag, and revokes all
existing root sessions atomically. Only operators with access to the server/container
and its database configuration can run it. Do not write a plaintext password directly
into `users.password_hash`.

### Verification

Run the normal API suite with `python -m pytest tests -q`. Tests use a fresh temporary
SQLite database instead of the application's data. Server-rendered compatibility
UI tests are marked `legacy_ui`; use `TEST_LEGACY_UI=1` to run those separately.
`tests/test_workspace_purge.py` enables SQLite foreign keys to verify deletion order
and preservation of another workspace. PostgreSQL deletion checks run in CI using
`TEST_DELETE_DATABASE_URL` against a dedicated disposable database.

From `dashboard-ui`, run `npm run build` for TypeScript and the production bundle.
Local implementation work does not deploy the app or migrate any running production
database. Startup applies additive schema upgrades; back up an existing database
before installing an update and follow your normal deployment process.
