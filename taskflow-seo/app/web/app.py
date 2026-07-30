from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.database import close_db, init_db
from app.scheduler.scheduler import start_scheduler, stop_scheduler
from app.web.templates_setup import templates

_base = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.DATABASE_URL.startswith('sqlite+aiosqlite:///'):
        db_path = Path(settings.DATABASE_URL.replace('sqlite+aiosqlite:///', ''))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Path(settings.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

    log_handler = RotatingFileHandler(
        settings.LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8',
    )
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            log_handler,
            logging.StreamHandler(),
        ],
        force=True,
    )

    await init_db()
    await start_scheduler()
    yield
    await stop_scheduler()
    await close_db()


app = FastAPI(title='TaskFlow-SEO', lifespan=lifespan)

static_dir = _base / 'static'
static_dir.mkdir(exist_ok=True)
app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')


if os.getenv('TASKFLOW_LEGACY_UI') == '1':
    from app.web.router import router
    from app.web.user_routes import router as user_router

    app.include_router(router)
    app.include_router(user_router)

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
