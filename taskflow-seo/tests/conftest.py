import asyncio
import os

os.environ['TESTING'] = '1'
os.environ['TASKFLOW_LEGACY_UI'] = '1'
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///./data/test.db'
os.environ['WEB_APP_SECRET'] = 'test-secret-for-testing'
os.environ['CRYPTO_SECRET'] = 'test-crypto-secret'
os.environ['LOG_LEVEL'] = 'WARNING'
os.environ['OVERDUE_CHECK_INTERVAL_SECONDS'] = '3600'

import pytest
from httpx import AsyncClient, ASGITransport


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
    async with AsyncClient(transport=transport, base_url='http://test', follow_redirects=False) as ac:
        yield ac
    await close_db()


@pytest.fixture(scope='session')
async def admin_cookies(client):
    resp = await client.post(
        '/api/auth/login',
        json={'username': 'admin', 'password': 'admin'}
    )
    assert resp.status_code == 200, f'Login failed: {resp.status_code} {resp.text}'
    return {'taskflow_user': resp.cookies.get('taskflow_user')}


@pytest.fixture(scope='session')
async def executor_cookies(client):
    from app.core.auth import hash_password
    from app.core.database import async_session
    from app.core.models import Role, User, UserRole
    from sqlalchemy import select

    async with async_session() as session:
        existing = (await session.execute(
            select(User).where(User.username == 'testexec')
        )).scalar_one_or_none()
        if not existing:
            existing = User(username='testexec', password_hash=hash_password('testpass'))
            session.add(existing)
            await session.commit()
            await session.refresh(existing)

        executor_role = (await session.execute(
            select(Role).where(Role.name == 'executor')
        )).scalar_one_or_none()
        if executor_role:
            link = (await session.execute(
                select(UserRole).where(
                    UserRole.user_id == existing.id,
                    UserRole.role_id == executor_role.id,
                )
            )).scalar_one_or_none()
            if not link:
                session.add(UserRole(user_id=existing.id, role_id=executor_role.id))
                await session.commit()

    resp = await client.post(
        '/api/auth/login',
        json={'username': 'testexec', 'password': 'testpass'}
    )
    assert resp.status_code == 200, f'Executor login failed: {resp.status_code} {resp.text}'
    return {'taskflow_user': resp.cookies.get('taskflow_user')}


@pytest.fixture
def sync_request(client, event_loop):
    def make_request(method, url, **kw):
        if 'cookies' in kw:
            c = kw.pop('cookies')
            kw.setdefault('headers', {})['Cookie'] = '; '.join(
                f'{k}={v}' for k, v in c.items()
            ) if c else ''
        return event_loop.run_until_complete(client.request(method, url, **kw))
    return make_request
