"""Recovery must never silently grant permissions or bypass management scope."""
import json
import uuid
from sqlalchemy import select
from app.core.database import async_session
from app.core.models import Role, Group, User, UserRole, UserGroup, WorkspaceMember
from app.core.permissions import get_user_permissions


def target_id(sync_request, cookies):
    return next(user['id'] for user in sync_request('GET', '/api/users', cookies=cookies).json() if user['username'] == 'testexec')


def test_global_role_delete_restore_without_assignments(sync_request, admin_cookies, executor_cookies, event_loop):
    uid = target_id(sync_request, admin_cookies)
    role = sync_request('POST', '/api/roles', json={'name': 'recover_'+uuid.uuid4().hex[:8], 'permissions': {'workspaces_create': True}}, cookies=admin_cookies).json()
    rid = role['id']
    async def link():
        async with async_session() as session:
            session.add(UserRole(user_id=uid, role_id=rid)); await session.commit()
        assert (await get_user_permissions(uid)).get('workspaces_create')
    event_loop.run_until_complete(link())
    assert sync_request('DELETE', f'/api/roles/{rid}', cookies=executor_cookies).status_code == 403
    assert sync_request('DELETE', f'/api/roles/{rid}', cookies=admin_cookies).status_code == 200
    assert not any(item['id'] == rid for item in sync_request('GET', '/api/roles', cookies=admin_cookies).json())
    assert any(item['id'] == rid for item in sync_request('GET', '/api/roles?deleted=true', cookies=admin_cookies).json())
    assert sync_request('PUT', f'/api/users/{uid}/role', json={'role_id': rid}, cookies=admin_cookies).status_code == 404
    assert sync_request('POST', f'/api/roles/{rid}/restore', cookies=executor_cookies).status_code == 403
    assert sync_request('POST', f'/api/roles/{rid}/restore', cookies=admin_cookies).status_code == 200
    async def verify():
        async with async_session() as session:
            assert (await session.get(Role, rid)).deleted_at is None
            assert not await session.scalar(select(UserRole.id).where(UserRole.user_id == uid, UserRole.role_id == rid))
        assert not (await get_user_permissions(uid)).get('workspaces_create')
    event_loop.run_until_complete(verify())


def test_group_delete_restore_removes_members(sync_request, admin_cookies, executor_cookies, event_loop):
    uid = target_id(sync_request, admin_cookies)
    group = sync_request('POST', '/api/groups', json={'name': 'recover_'+uuid.uuid4().hex[:8], 'permissions': {'workspaces_create': True}}, cookies=admin_cookies).json()
    gid = group['id']
    assert sync_request('PUT', f'/api/groups/{gid}/members', json={'user_ids': [uid]}, cookies=admin_cookies).status_code == 200
    assert sync_request('DELETE', f'/api/groups/{gid}', cookies=admin_cookies).status_code == 200
    assert any(item['id'] == gid for item in sync_request('GET', '/api/groups?deleted=true', cookies=admin_cookies).json())
    assert sync_request('PUT', f'/api/groups/{gid}/members', json={'user_ids': [uid]}, cookies=admin_cookies).status_code == 404
    assert sync_request('POST', f'/api/groups/{gid}/restore', cookies=executor_cookies).status_code == 403
    assert sync_request('POST', f'/api/groups/{gid}/restore', cookies=admin_cookies).status_code == 200
    restored = next(item for item in sync_request('GET', '/api/groups', cookies=admin_cookies).json() if item['id'] == gid)
    assert restored['user_ids'] == [] and restored['permissions']['workspaces_create']
    async def verify():
        async with async_session() as session:
            assert not await session.scalar(select(UserGroup.id).where(UserGroup.group_id == gid))
        assert not (await get_user_permissions(uid)).get('workspaces_create')
    event_loop.run_until_complete(verify())


def test_workspace_role_recovery_scope_and_in_use_guard(sync_request, admin_cookies, executor_cookies):
    uid = target_id(sync_request, admin_cookies)
    ws = sync_request('POST', '/api/workspaces', json={'name': 'Recovery '+uuid.uuid4().hex[:8], 'preset': 'study'}, cookies=admin_cookies).json()
    wid = ws['id']
    assert sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid, 'role': 'member'}, cookies=admin_cookies).status_code == 201
    role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': 'Recoverable', 'permissions': {'tasks': True}}, cookies=admin_cookies).json()
    rid = role['id']
    path = f'/api/workspaces/{wid}/roles/{rid}'
    assert sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': rid}, cookies=admin_cookies).status_code == 200
    assert sync_request('DELETE', path, cookies=admin_cookies).status_code == 409
    assert sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': None}, cookies=admin_cookies).status_code == 200
    assert sync_request('DELETE', path, cookies=executor_cookies).status_code == 403
    assert sync_request('DELETE', path, cookies=admin_cookies).status_code == 200
    assert sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': rid}, cookies=admin_cookies).status_code == 404
    assert sync_request('POST', path+'/restore', cookies=executor_cookies).status_code == 403
    assert sync_request('POST', f'/api/workspaces/1/roles/{rid}/restore', cookies=admin_cookies).status_code == 404
    archived = sync_request('GET', f'/api/workspaces/{wid}/roles?deleted=true', cookies=admin_cookies).json()['roles']
    assert any(item['id'] == rid for item in archived)
    assert sync_request('POST', path+'/restore', cookies=admin_cookies).status_code == 200
    assert any(item['id'] == rid for item in sync_request('GET', f'/api/workspaces/{wid}/roles', cookies=admin_cookies).json()['roles'])


def test_system_role_cannot_be_deleted(sync_request, admin_cookies):
    root_role = next(item for item in sync_request('GET', '/api/roles', cookies=admin_cookies).json() if item['name'] == 'superadmin')
    assert sync_request('DELETE', f"/api/roles/{root_role['id']}", cookies=admin_cookies).status_code == 403


def test_stale_archived_workspace_binding_denies_all_work(sync_request, admin_cookies, executor_cookies, event_loop):
    from app.core.models import WorkspaceRole
    from app.core.permissions import get_workspace_permissions
    from app.core.access_policy import field_access
    uid = target_id(sync_request, admin_cookies)
    ws = sync_request('POST', '/api/workspaces', json={'name': 'Stale '+uuid.uuid4().hex[:8], 'preset': 'study'}, cookies=admin_cookies).json()
    wid = ws['id']
    sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid, 'role': 'member'}, cookies=admin_cookies)
    role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': 'Stale', 'permissions': {'tasks': True}}, cookies=admin_cookies).json()
    rid = role['id']
    assert sync_request('DELETE', f'/api/workspaces/{wid}/roles/{rid}', cookies=admin_cookies).status_code == 200
    async def stale():
        async with async_session() as session:
            member = await session.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == wid, WorkspaceMember.user_id == uid))
            member.custom_role_id = rid
            user = await session.get(User, uid)
            await session.commit()
        assert await get_workspace_permissions(uid, wid) == {}
        assert all(mode == 'hidden' for fields in (await field_access(user, wid)).values() for mode in fields.values())
    event_loop.run_until_complete(stale())
    assert sync_request('POST', f'/api/workspaces/{wid}/roles/{rid}/restore', cookies=admin_cookies).status_code == 409


def test_workspace_admin_restore_respects_permission_ceiling(sync_request, admin_cookies):
    ws = sync_request('POST', '/api/workspaces', json={'name': 'Ceiling '+uuid.uuid4().hex[:8], 'preset': 'seo'}, cookies=admin_cookies).json()
    wid = ws['id']
    username = 'restore_admin_'+uuid.uuid4().hex[:8]
    created = sync_request('POST', '/api/users', json={'username': username, 'password': 'pass1234', 'must_change_password': False}, cookies=admin_cookies)
    assert created.status_code == 201
    uid = created.json()['id']
    login = sync_request('POST', '/api/auth/login', json={'username': username, 'password': 'pass1234'})
    assert login.status_code == 200
    cookies = {'taskflow_user': login.cookies.get('taskflow_user')}
    sync_request('POST', f'/api/workspaces/{wid}/members', json={'user_id': uid, 'role': 'admin'}, cookies=admin_cookies)
    profile = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': 'Limited manager', 'permissions': {'workspace_profiles': True, 'tasks': True}}, cookies=admin_cookies).json()
    assert sync_request('PUT', f'/api/workspaces/{wid}/members/{uid}/custom-role', json={'role_id': profile['id']}, cookies=admin_cookies).status_code == 200
    for name, permissions, expected in [('Allowed', {'tasks': True}, 200), ('Higher', {'tasks': True, 'reports': True}, 403)]:
        role = sync_request('POST', f'/api/workspaces/{wid}/roles', json={'name': name, 'permissions': permissions}, cookies=admin_cookies).json()
        path = f"/api/workspaces/{wid}/roles/{role['id']}"
        assert sync_request('DELETE', path, cookies=admin_cookies).status_code == 200
        assert sync_request('POST', path+'/restore', cookies=cookies).status_code == expected


def test_old_database_access_archive_migration(tmp_path, monkeypatch, event_loop):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core import database

    old_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old-access.db'}")
    monkeypatch.setattr(database, 'engine', old_engine)
    monkeypatch.setattr(database.settings, 'DATABASE_URL', 'sqlite+aiosqlite:///old-access.db')

    async def check():
        try:
            async with old_engine.begin() as conn:
                for table in ('roles', 'groups', 'workspace_roles'):
                    await conn.execute(text(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, name TEXT)'))
                    await conn.execute(text(f"INSERT INTO {table} VALUES (1, 'existing')"))
            await database._migrate()
            await database._migrate()  # Startup migrations must be repeatable.
            async with old_engine.connect() as conn:
                for table in ('roles', 'groups', 'workspace_roles'):
                    row = (await conn.execute(text(f'SELECT name, deleted_at FROM {table} WHERE id=1'))).one()
                    assert row == ('existing', None)
        finally:
            await old_engine.dispose()

    event_loop.run_until_complete(check())
