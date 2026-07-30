# TaskFlow Dashboard

TaskFlow Dashboard is an internal CRM and task management system for SEO, content, development and client operations teams. The project combines task planning, Kanban, calendar scheduling, client records, contracts, files, reports, notifications, role-based permissions and local AI-assisted workflows in one web application.

The application was designed for a small team working with many client organizations where it is important to see tasks, deadlines, completed work, client access data, contract state and operational history in one place.

## Features

- Task management with statuses, priorities, task types, assignees and multiple co-assignees.
- Calendar view based on task execution date, with drag-and-drop date changes.
- Kanban board with drag-and-drop status changes, date filtering and collapsible columns.
- Client database with organizations, contacts, contracts, notes, access credentials, files and favicon detection.
- Role and permission system with section-level and tab-level access control.
- Personal and team task visibility modes: own tasks, all tasks, selected users, created tasks and co-assigned tasks.
- Saved task and Kanban views.
- Notifications for assignments, overdue tasks and system events.
- Trash for deleted tasks, clients and reports.
- Client analytics by selected period: completed tasks, active tasks, overdue tasks, task types and connected modules.
- Module automation for recurring task generation.
- Detailed task and client activity history.
- File attachments for tasks, clients and contracts, including pasted screenshots.
- HTML reports based on completed work.
- Local AI assistant integration for task creation, text cleanup and report drafting.

## Tech Stack

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- Tiptap rich text editor
- dnd-kit for drag-and-drop
- Recharts for analytics charts
- lucide-react for icons

### Backend

- Python
- FastAPI
- SQLAlchemy async ORM
- Alembic migrations
- APScheduler background jobs
- Pydantic settings
- PostgreSQL through `asyncpg`

### Optional / Local Services

- PostgreSQL for application data.
- Ollama for local LLM features.
- Local filesystem storage for uploaded files and generated reports.

## Architecture

```text
TaskFlow Dashboard
├── dashboard-ui/          # React + Vite frontend
│   ├── src/api/           # API client and frontend cache helpers
│   ├── src/components/    # Shared UI components
│   ├── src/pages/         # Main application screens
│   └── src/lib/           # UI metadata, formatting and utilities
│
├── taskflow-seo/          # FastAPI backend
│   ├── app/core/          # Config, database, models, auth and permissions
│   ├── app/services/      # Business logic services
│   ├── app/scheduler/     # Background jobs
│   ├── app/web/api/       # REST API routers
│   ├── alembic/           # Database migrations
│   └── tests/             # Backend tests
│
├── docs/                  # Project notes and documentation
├── data/                  # Local runtime data, ignored by Git
├── logs/                  # Runtime logs, ignored by Git
└── backups/               # Local backups, ignored by Git
```

## Main Modules

### Dashboard

Shows a high-level overview of active work, overdue tasks, client health and important operational indicators.

### Tasks

The central task list. Supports filtering, saved views, mass updates, attachments, comments, rich text fields, client access data and activity history.

### Calendar

Displays tasks by execution date, not by deadline. Tasks can be moved between days by drag-and-drop. If a day has many tasks, the month cell shows the first items and opens a full day list.

### Kanban

Visual workflow board grouped by task status. Dragging a card changes its status. Columns can be collapsed when a status contains many tasks.

### Clients

Stores organizations, contacts, contracts, notes, access credentials, files and related tasks. Client access data can be attached to specific tasks without exposing all credentials by default.

### Reports

Generates HTML reports based on completed work for the selected client and period. Reports can be stored, viewed and deleted.

### Modules

Automates recurring operational tasks. A module can create scheduled tasks for one or multiple clients using configured templates and dates.

### Users and Permissions

Supports role-based permissions for sections, client tabs and task visibility. Super administrator has full access and is treated as the application owner.

## Requirements

- Windows, Linux or macOS
- Python 3.12+
- Node.js 20+
- PostgreSQL 16+
- Optional: Ollama for local AI features

## Environment Variables

Create `taskflow-seo/.env` from `taskflow-seo/.env.example`.

```env
DATABASE_URL=postgresql+asyncpg://taskflow:taskflow@localhost:5432/taskflow
DEFAULT_TIMEZONE=Europe/Moscow
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
WEB_APP_SECRET=change-this-secret
CRYPTO_SECRET=change-this-crypto-secret
OVERDUE_CHECK_INTERVAL_SECONDS=60
CONTRACT_REMINDER_DAYS=[14,7,3,1]
DEFAULT_REMINDER_OFFSET_HOURS=1
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
```

Important:

- Never commit `.env`.
- Change `WEB_APP_SECRET` and `CRYPTO_SECRET` before real use.
- Keep database backups outside the public repository.

## Local Development

### Backend

```bash
cd taskflow-seo
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.web.app:app --host 0.0.0.0 --port 8080 --reload
```

Backend API will be available at:

```text
http://127.0.0.1:8080
```

### Frontend

```bash
cd dashboard-ui
npm install
npm run dev
```

Frontend will be available at:

```text
http://127.0.0.1:3000
```

Vite proxies `/api`, `/login` and `/logout` to the backend on port `8080`.

## Production Build

Build the frontend:

```bash
cd dashboard-ui
npm run build
```

The production frontend is generated in:

```text
dashboard-ui/dist
```

For daily local-network use, it is better to run the built production frontend instead of the Vite development server. This reduces CPU and memory usage and makes the application more stable for other users on the same LAN.

## Docker

The backend includes a Docker setup with PostgreSQL:

```bash
cd taskflow-seo
docker compose up -d --build
```

Docker Compose starts:

- `postgres` database service
- `web` FastAPI service

## AI Features

The project can use a local Ollama server for AI-assisted operations:

- creating task drafts from natural language;
- cleaning and formatting text;
- assisting with report content;
- improving descriptions and comments.

AI is optional. Core CRM, task, calendar and reporting features work without Ollama.

## File Storage

Uploaded files, pasted screenshots and generated files are stored locally on the server. Runtime files should not be committed to Git.

Recommended ignored folders:

- `data/`
- `logs/`
- `backups/`
- uploaded files storage folders

## Testing and Quality

Backend:

```bash
cd taskflow-seo
pytest
ruff check .
```

Frontend:

```bash
cd dashboard-ui
npm run build
npm run lint
```

## GitHub Preparation

Before publishing:

1. Check that `.env` files are not committed.
2. Remove local virtual environments and dependency folders.
3. Remove logs, temporary files, local databases and backups.
4. Keep `package-lock.json` or `pnpm-lock.yaml`, but do not keep both unless the project intentionally supports both package managers.
5. Run production build and backend checks.
6. Review `git status` before the first commit.

## Do Not Commit

- `.env`
- PostgreSQL dumps with real data
- SQLite databases
- uploaded user files
- logs
- backups
- `node_modules`
- `dist`
- `venv` / `.venv`
- IDE folders

## License

No license has been selected yet. Add a license before publishing the repository if the project should be open source.
