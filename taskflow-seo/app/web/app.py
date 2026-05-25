from __future__ import annotations
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.database import init_db, close_db

templates_dir = Path(__file__).parent / 'templates'
templates = Jinja2Templates(directory=str(templates_dir))


@asynccontextmanager
async def lifespan(app: FastAPI):
    for path in ['data', 'logs']:
        Path(path).mkdir(exist_ok=True)
    await init_db()
    yield
    await close_db()


app = FastAPI(title='TaskFlow-SEO', lifespan=lifespan)

static_dir = Path(__file__).parent / 'static'
static_dir.mkdir(exist_ok=True)
app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')

SECRET_COOKIE = 'taskflow_token'
AUTH_TOKEN = settings.WEB_APP_SECRET or 'taskflow_secret_2026'


def check_auth(request: Request) -> bool:
    return request.cookies.get(SECRET_COOKIE) == AUTH_TOKEN


async def get_db():
    from app.core.database import async_session
    async with async_session() as session:
        yield session


from app.web.router import router
app.include_router(router)
