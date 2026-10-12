import asyncio
import hashlib
import importlib
import json
import sqlite3
import uuid

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from app.core.auth import hash_password, verify_password, password_needs_upgrade, set_session_cookie
from app.core.config import settings
from app.core.database import async_session
from app.core.models import User, Client, LoginThrottle
from tests.test_user_deletion import deletion_db


def legacy_hash(password):
    salt = 'a' * 32
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()


def test_stronger_hash_accepts_old_and_new_passwords_without_accepting_malformed_hashes():
    old = legacy_hash('known-password')
    new = hash_password('known-password')
    assert verify_password('known-password', old) and verify_password('known-password', new)
    assert password_needs_upgrade(old) and not password_needs_upgrade(new)
    assert not verify_password('wrong', new)
    for stored in ('invalid', 'pbkdf2_sha256$999999999$' + 'a'*32 + '$' + 'a'*64, 'a:1', None):
        assert not verify_password('known-password', stored)


@pytest.mark.asyncio
async def test_successful_login_upgrades_hash_without_changing_password_or_revoking_sessions(client):
    from app.services.user_service import authenticate
    name = 'upgrade_' + uuid.uuid4().hex
    async with async_session() as session:
        user = User(username=name, password_hash=legacy_hash('known-password'), session_version=77)
        session.add(user); await session.commit(); uid = user.id
    assert await authenticate(name, 'wrong') is None
    result = await authenticate(name, 'known-password')
    assert result.id == uid and result.session_version == 77
    async with async_session() as session:
        saved = await session.get(User, uid)
        assert not password_needs_upgrade(saved.password_hash)
        assert verify_password('known-password', saved.password_hash)
        assert saved.session_version == 77


@pytest.mark.parametrize('secure', [True, False])
def test_all_session_cookie_flags_are_consistent(monkeypatch, secure):
    monkeypatch.setattr(settings, 'COOKIE_SECURE', secure)
    response = JSONResponse({'ok': True})
    set_session_cookie(response, 1, 2)
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie and 'Path=/' in cookie
    assert ('Secure' in cookie) == secure


@pytest.mark.asyncio
async def test_rate_limit_is_atomic_persistent_and_expires(monkeypatch, client):
    import app.web.security as security
    name = 'parallel_' + uuid.uuid4().hex
    async def reserve():
        try:
            await security.check_login_limit(name)
            return True
        except HTTPException as error:
            assert error.status_code == 429
            return False
    results = await asyncio.gather(*(reserve() for _ in range(15)))
    assert sum(results) == 10
    importlib.reload(security)
    with pytest.raises(HTTPException):
        await security.check_login_limit(name.upper())
    now = security.time.time()
    monkeypatch.setattr(security.time, 'time', lambda: now + 901)
    await security.check_login_limit(name)
    await security.login_succeeded(name)
    async with async_session() as session:
        assert await session.get(LoginThrottle, security._login_key(name)) is None


@pytest.mark.asyncio
async def test_legacy_access_encryption_preserves_data_and_is_idempotent(client):
    from app.core.access_migration import migrate_legacy_client_accesses
    from app.core.utils.crypto import decrypt_accesses_value
    original = [{'title': 'Test', 'login': 'user', 'password': 'private-regression-value'}]
    async with async_session() as session:
        from app.core.utils.timezone import utc_now
        client = Client(org_name='Migration '+uuid.uuid4().hex, accesses=json.dumps(original), contract_start=utc_now(), contract_end=utc_now())
        session.add(client); await session.commit(); cid = client.id
    await migrate_legacy_client_accesses()
    async with async_session() as session:
        protected = (await session.get(Client, cid)).accesses
        assert 'private-regression-value' not in protected
        assert decrypt_accesses_value(protected) == original
    await migrate_legacy_client_accesses()
    async with async_session() as session:
        assert (await session.get(Client, cid)).accesses == protected


def test_backup_is_encrypted_by_default_and_restorable(tmp_path):
    import base64
    from cryptography.fernet import Fernet
    from scripts.backup_db import backup
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE records (value TEXT)')
        conn.execute("INSERT INTO records VALUES ('private-regression-value')")
    key = 'k'*32
    target = backup('sqlite+aiosqlite:///'+str(source), tmp_path/'backups', crypto_secret=key)
    assert target.suffix == '.fernet'
    assert b'private-regression-value' not in target.read_bytes()
    assert list((tmp_path/'backups').iterdir()) == [target]
    restored = tmp_path/'restored.db'
    restored.write_bytes(Fernet(base64.urlsafe_b64encode(key.encode())).decrypt(target.read_bytes()))
    with sqlite3.connect(restored) as conn:
        assert conn.execute('SELECT value FROM records').fetchone()[0] == 'private-regression-value'
    with pytest.raises(ValueError):
        backup('sqlite+aiosqlite:///'+str(source), tmp_path/'backups', crypto_secret='')


@pytest.mark.asyncio
async def test_legacy_helper_rejects_revoked_sessions_and_root_password_change(monkeypatch):
    from starlette.requests import Request
    from app.core.auth import make_session_token
    import app.web.user_routes as routes
    user = User(id=9876, username='root-regression', is_active=True, is_root=True, session_version=5)
    async def lookup(uid):
        return user
    monkeypatch.setattr(routes, 'get_user', lookup)
    def request(version):
        token = make_session_token(user.id, version)
        return Request({'type':'http', 'headers':[(b'cookie', ('taskflow_user='+token).encode())]})
    assert await routes._current_user(request(4)) is None
    assert await routes._current_user(request(5)) is user
    with pytest.raises(HTTPException) as denied:
        await routes.api_change_password(request(5), 'old-password', 'new-password')
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_database_exceptions_hide_bound_secret_values(client):
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    async with async_session() as session:
        with pytest.raises(SQLAlchemyError) as error:
            await session.execute(text('SELECT :value FROM security_missing_table'), {'value': 'private-regression-value'})
        assert 'private-regression-value' not in str(error.value)


@pytest.mark.asyncio
async def test_shared_throttle_and_access_migration_on_deployment_database(deletion_db, monkeypatch):
    import app.core.database as database
    import app.web.security as security
    import app.core.access_migration as migration
    from app.core.utils.crypto import decrypt_accesses_value
    from datetime import datetime
    monkeypatch.setattr(database, 'async_session', deletion_db)
    monkeypatch.setattr(migration, 'async_session', deletion_db)
    dialect = deletion_db.kw['bind'].dialect.name
    monkeypatch.setattr(settings, 'DATABASE_URL', 'sqlite+aiosqlite://' if dialect == 'sqlite' else 'postgresql+asyncpg://')
    name = 'engine_' + uuid.uuid4().hex
    async def reserve():
        try:
            await security.check_login_limit(name)
            return True
        except HTTPException as error:
            assert error.status_code == 429
            return False
    assert sum(await asyncio.gather(*(reserve() for _ in range(15)))) == 10
    await security.login_succeeded(name)
    async with deletion_db() as session:
        client = Client(org_name='Encrypted on '+dialect, contract_start=datetime(2026,1,1), contract_end=datetime(2027,1,1), accesses=json.dumps([{'password':'private-regression-value'}]))
        session.add(client); await session.commit(); cid = client.id
    assert await migration.migrate_legacy_client_accesses() == 1
    async with deletion_db() as session:
        protected = (await session.get(Client, cid)).accesses
        assert 'private-regression-value' not in protected
        assert decrypt_accesses_value(protected) == [{'password':'private-regression-value'}]


def test_login_validation_never_echoes_submitted_password(sync_request):
    secret = 'private-regression-value-' * 40
    response = sync_request('POST', '/api/auth/login', json={'username': 'validation-test', 'password': secret})
    assert response.status_code == 422
    assert secret not in response.text
    assert all('input' not in detail for detail in response.json()['detail'])
