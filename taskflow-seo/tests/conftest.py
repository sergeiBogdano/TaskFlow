import asyncio
import os
import pytest
from pathlib import Path

_saved_db_url = os.environ.get('DATABASE_URL')
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///./data/test.db'

from httpx import AsyncClient, ASGITransport


def _cookies_header(cookies: dict) -> dict:
    return {'Cookie': '; '.join(f'{k}={v}' for k, v in cookies.items())} if cookies else {}


@pytest.fixture(scope='session')
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope='session')
async def client(event_loop):
    from app.web.app import app
    from app.core.database import init_db, close_db
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        yield ac
    await close_db()
    # Restore original DATABASE_URL so production DB is not affected
    if _saved_db_url is None:
        os.environ.pop('DATABASE_URL', None)
    else:
        os.environ['DATABASE_URL'] = _saved_db_url


@pytest.fixture(scope='session')
async def admin_cookies(client):
    resp = await client.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
    assert resp.status_code == 302
    return dict(resp.cookies)



