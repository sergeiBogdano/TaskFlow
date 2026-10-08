from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session, close_db, init_db
from app.scheduler.scheduler import start_scheduler, stop_scheduler
from app.web.templates_setup import templates


_base = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_runtime_secrets()
    if settings.DATABASE_URL.startswith("sqlite+aiosqlite:///"):
        db_path = Path(
            settings.DATABASE_URL.replace(
                "sqlite+aiosqlite:///",
                "",
            )
        )
        db_path.parent.mkdir(parents=True, exist_ok=True)

    handlers = [logging.StreamHandler()]
    file_logging_unavailable = False
    try:
        Path(settings.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        handlers.insert(0, RotatingFileHandler(
            settings.LOG_FILE, maxBytes=10 * 1024 * 1024,
            backupCount=5, encoding="utf-8",
        ))
    except PermissionError:
        # Existing Docker volumes may contain root-owned logs from an older image.
        # Container stdout stays available without restoring root privileges.
        file_logging_unavailable = True

    logging.basicConfig(
        level=getattr(
            logging,
            settings.LOG_LEVEL.upper(),
            logging.INFO,
        ),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    if file_logging_unavailable:
        logging.warning('File logging is unavailable; using console. Check logs volume permissions for UID 10001.')

    await init_db()
    await start_scheduler()
    from app.core.ai_assistant import start_worker, stop_worker
    start_worker()

    yield

    await stop_scheduler()
    await stop_worker()
    await close_db()


app = FastAPI(
    title="TaskFlow",
    version="1.0.0-alpha.1",
    lifespan=lifespan,
)

# work-права активного окружения → 403 для закрытых разделов API (Ф8)
from app.web.middleware import work_permission_middleware  # noqa: E402

app.middleware("http")(work_permission_middleware)
from app.web.security import security_headers, RequestSizeLimit
app.middleware("http")(security_headers)
app.add_middleware(RequestSizeLimit)


@app.get("/health")
async def health():
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "ok",
        }

    except Exception:
        logging.exception("Health check failed")

        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "database": "unavailable",
            },
        )


static_dir = _base / "static"
static_dir.mkdir(exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory=str(static_dir)),
    name="static",
)


from app.web.api.auth import router as auth_router
from app.web.api.users import router as users_router
from app.web.api.roles import router as roles_router
from app.web.api.clients import router as clients_router
from app.web.api.tasks import router as tasks_router
from app.web.api.modules import router as modules_router
from app.web.api.dashboard import router as dashboard_router
from app.web.api.calendar import router as calendar_router
from app.web.api.notifications import router as notifications_router
from app.web.api.saved_views import router as saved_views_router
from app.web.api.quick_tasks import router as quick_tasks_router
from app.web.api.reports import router as reports_router
from app.web.api.ai import router as ai_router
from app.web.api.ai_analytics import router as ai_analytics_router
from app.web.api.assistant import router as assistant_router
from app.web.api.workspaces import router as workspaces_router
from app.web.api.sprints import router as sprints_router
from app.web.api.notes import router as notes_router
from app.web.api.permissions import router as permissions_router
from app.web.api.groups import router as groups_router
from app.web.api.features import router as features_router
from app.web.api.workspace_roles import router as workspace_roles_router
from app.web.api.workspace_access import router as workspace_access_router


from app.web.api.crm import router as crm_router
# Preserve API helpers that originally lived beside Jinja pages, without letting
# their duplicate CRUD handlers shadow the production API.
from fastapi import APIRouter
from app.web.router import router as legacy_router
_api_routers = (auth_router, users_router, roles_router, clients_router, tasks_router,
    modules_router, dashboard_router, calendar_router, notifications_router, saved_views_router,
    quick_tasks_router, reports_router, ai_router, ai_analytics_router, assistant_router, workspaces_router,
    sprints_router, notes_router, permissions_router, groups_router, features_router,
    workspace_roles_router, workspace_access_router, crm_router)
_signatures = {(method, route.path) for router in _api_routers for route in router.routes
               if hasattr(route, 'methods') for method in route.methods}
helpers = APIRouter()
for route in legacy_router.routes:
    if getattr(route, 'path', '').startswith('/api/') and not any(
            (method, route.path) in _signatures for method in getattr(route, 'methods', [])):
        helpers.routes.append(route)
app.include_router(helpers)


app.include_router(crm_router)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(clients_router)
app.include_router(tasks_router)
app.include_router(modules_router)
app.include_router(dashboard_router)
app.include_router(calendar_router)
app.include_router(notifications_router)
app.include_router(saved_views_router)
app.include_router(quick_tasks_router)
app.include_router(reports_router)
app.include_router(ai_router)
app.include_router(ai_analytics_router)
app.include_router(assistant_router)
app.include_router(workspaces_router)
app.include_router(sprints_router)
app.include_router(notes_router)
app.include_router(permissions_router)
app.include_router(groups_router)
app.include_router(features_router)
app.include_router(workspace_roles_router)
app.include_router(workspace_access_router)

if os.getenv('TASKFLOW_LEGACY_UI') == '1':
    from app.web.user_routes import router as user_router
    app.include_router(legacy_router)
    app.include_router(user_router)
