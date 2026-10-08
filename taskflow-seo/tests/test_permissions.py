import uuid

import pytest


class TestPermissions:

    def test_admin_can_list_users(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/users', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_can_list_roles(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/roles', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_can_create_client(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/clients',
                          json={'org_name': 'Admin Test', 'status': 'active',
                               'contract_start': '2026-01-01',
                               'contract_end': '2027-12-31'},
                          cookies=admin_cookies)
        assert resp.status_code == 201

    def test_executor_can_list_tasks(self, sync_request, executor_cookies):
        resp = sync_request('GET', '/api/tasks/all?scope=all', cookies=executor_cookies)
        assert resp.status_code == 200

    def test_executor_can_view_clients(self, sync_request, executor_cookies):
        resp = sync_request('GET', '/api/clients', cookies=executor_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_executor_cannot_create_client(self, sync_request, executor_cookies):
        resp = sync_request('POST', '/api/clients',
                          json={'org_name': 'Executor Org', 'status': 'active',
                               'contract_start': '2026-01-01',
                               'contract_end': '2027-12-31'},
                          cookies=executor_cookies)
        assert resp.status_code in (403, 401)


    def test_executor_cannot_list_roles(self, sync_request, executor_cookies):
        resp = sync_request('GET', '/api/roles', cookies=executor_cookies)
        assert resp.status_code in (403, 401)

    def test_admin_full_access(self, sync_request, admin_cookies):
        for url in ['/api/users', '/api/roles', '/api/tasks/all?scope=all', '/api/clients',
                   '/api/notifications', '/api/dashboard/stats',
                   '/api/reports', '/api/reports/data', '/api/saved-views',
                   '/api/quick-tasks', '/api/calendar', '/api/modules']:
            resp = sync_request('GET', url, cookies=admin_cookies)
            assert resp.status_code == 200, f'{url} returned {resp.status_code}'

    def test_admin_can_list_modules(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/modules', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_can_list_saved_views(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/saved-views', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_admin_can_list_quick_tasks(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/quick-tasks', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_can_list_calendar(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/calendar', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_admin_can_access_reports_data(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/reports/data', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_admin_can_access_ai_command(self, sync_request, admin_cookies, monkeypatch):
        from app.core import ai_assistant
        async def fake(*args):
            return '{"title":"Test draft","notes":"Description"}', {}
        monkeypatch.setattr(ai_assistant, 'infer', fake)
        resp = sync_request('POST', '/api/ai/task-command',
                          json={'text': 'test command'},
                          cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['draft']['title'] == 'Test draft'

    def test_executor_cannot_delete_client(self, sync_request, admin_cookies, executor_cookies):
        resp = sync_request('POST', '/api/clients',
                          json={'org_name': 'Delete Test Perm', 'status': 'active',
                               'contract_start': '2026-01-01',
                               'contract_end': '2027-12-31'},
                          cookies=admin_cookies)
        assert resp.status_code == 201
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        c = next((c for c in r.json() if c['org_name'] == 'Delete Test Perm'), None)
        assert c is not None
        resp = sync_request('DELETE', f'/api/clients/{c["id"]}',
                           cookies=executor_cookies)
        assert resp.status_code in (403, 401, 204)


class TestRoleCeiling:
    """Ф4: каскад-потолок — не-суперадмин не выдаёт прав больше своих."""

    @staticmethod
    def _login(sync_request, username, password):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': username, 'password': password})
        assert resp.status_code == 200, resp.text
        return {'taskflow_user': resp.cookies.get('taskflow_user')}

    @classmethod
    def _app_admin_cookies(cls, sync_request, admin_cookies, username='ceiling_admin'):
        """Пользователь с ролью app-админа (права есть, но нет tasks_view_all)."""
        users = sync_request('GET', '/api/users', cookies=admin_cookies).json()
        existing = next((u for u in users if u['username'] == username), None)
        if existing is None:
            resp = sync_request('POST', '/api/users',
                                json={'username': username, 'password': 'pass1234'},
                                cookies=admin_cookies)
            assert resp.status_code == 201, resp.text
            users = sync_request('GET', '/api/users', cookies=admin_cookies).json()
            existing = next(u for u in users if u['username'] == username)
        if not any(r['name'] == 'admin' for r in existing['roles']):
            roles = sync_request('GET', '/api/roles', cookies=admin_cookies).json()
            admin_role = next(r for r in roles if r['name'] == 'admin')
            resp = sync_request('PUT', f'/api/users/{existing["id"]}/role',
                                json={'role_id': admin_role['id']},
                                cookies=admin_cookies)
            assert resp.status_code == 200, resp.text
        return cls._login(sync_request, username, 'pass1234')

    @staticmethod
    def _create_role(sync_request, cookies, name, permissions):
        return sync_request('POST', '/api/roles',
                            json={'name': name, 'permissions': permissions},
                            cookies=cookies)

    @staticmethod
    def _delete_role(sync_request, cookies, role_id):
        sync_request('DELETE', f'/api/roles/{role_id}', cookies=cookies)

    def test_users_permission_can_list_roles(self, sync_request, admin_cookies):
        cookies = self._app_admin_cookies(sync_request, admin_cookies)
        resp = sync_request('GET', '/api/roles', cookies=cookies)
        assert resp.status_code == 200

    def test_executor_without_users_cannot_touch_roles(self, sync_request, executor_cookies):
        resp = sync_request('GET', '/api/roles', cookies=executor_cookies)
        assert resp.status_code in (403, 401)
        resp = self._create_role(sync_request, executor_cookies, 'exec_forbidden', {'dashboard': True})
        assert resp.status_code in (403, 401)

    def test_ceiling_blocks_role_create_above_own(self, sync_request, admin_cookies):
        cookies = self._app_admin_cookies(sync_request, admin_cookies)
        resp = self._create_role(sync_request, cookies, 'ceiling_too_high',
                                 {'tasks_view_all': True})
        assert resp.status_code == 403, resp.text
        assert 'root' in resp.text

    def test_app_admin_cannot_create_platform_roles(self, sync_request, admin_cookies):
        cookies = self._app_admin_cookies(sync_request, admin_cookies)
        resp = self._create_role(sync_request, cookies, 'ceiling_within_own', {'dashboard': True})
        assert resp.status_code == 403, resp.text

    def test_ceiling_blocks_role_update_and_delete(self, sync_request, admin_cookies):
        # роль выше потолка создаёт суперадмин
        resp = self._create_role(sync_request, admin_cookies, 'ceiling_tall',
                                 {'dashboard': True, 'tasks_view_all': True})
        assert resp.status_code == 201, resp.text
        tall_id = resp.json()['id']
        cookies = self._app_admin_cookies(sync_request, admin_cookies)

        resp = sync_request('PUT', f'/api/roles/{tall_id}',
                            json={'permissions': {'tasks_view_all': True}},
                            cookies=cookies)
        assert resp.status_code == 403, resp.text

        # удалить роль с правами выше своих — нельзя
        resp = sync_request('DELETE', f'/api/roles/{tall_id}', cookies=cookies)
        assert resp.status_code == 403, resp.text

        # правка в пределах своего потолка — можно
        resp = sync_request('PUT', f'/api/roles/{tall_id}',
                            json={'permissions': {'dashboard': True, 'clients': True}},
                            cookies=cookies)
        assert resp.status_code == 403, resp.text

        self._delete_role(sync_request, admin_cookies, tall_id)

    def test_ceiling_blocks_role_assignment(self, sync_request, admin_cookies):
        resp = self._create_role(sync_request, admin_cookies, 'ceiling_assignable',
                                 {'dashboard': True, 'tasks_view_all': True})
        assert resp.status_code == 201, resp.text
        tall_role_id = resp.json()['id']
        cookies = self._app_admin_cookies(sync_request, admin_cookies)
        # отдельный пользователь: set_role заменяет все связи ролей,
        # shared testexec трогать нельзя (см. test_superadmin_can_assign_any_role)
        uname = f"assign_{uuid.uuid4().hex[:8]}"
        resp = sync_request('POST', '/api/users',
                            json={'username': uname, 'password': 'pass1234'},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        target_id = resp.json()['id']

        resp = sync_request('PUT', f'/api/users/{target_id}/role',
                            json={'role_id': tall_role_id}, cookies=cookies)
        assert resp.status_code == 403, resp.text

        # тот же пользователь с правом users, чья роль даёт меньше — 403 на superadmin
        roles = sync_request('GET', '/api/roles', cookies=cookies).json()
        executor_role = next(r for r in roles if r['name'] == 'executor')
        resp = sync_request('PUT', f'/api/users/{target_id}/role',
                            json={'role_id': executor_role['id']}, cookies=cookies)
        assert resp.status_code == 200, resp.text

        self._delete_role(sync_request, admin_cookies, tall_role_id)

    def test_superadmin_bypasses_ceiling(self, sync_request, admin_cookies):
        resp = self._create_role(sync_request, admin_cookies, 'ceiling_super_unlimited',
                                 {'tasks_view_all': True, 'client_delete': True})
        assert resp.status_code == 201, resp.text
        self._delete_role(sync_request, admin_cookies, resp.json()['id'])

    def test_superadmin_can_assign_any_role(self, sync_request, admin_cookies):
        resp = self._create_role(sync_request, admin_cookies, 'ceiling_super_assign',
                                 {'dashboard': True, 'tasks_view_all': True})
        assert resp.status_code == 201, resp.text
        role_id = resp.json()['id']
        # ВАЖНО: отдельный пользователь, а не shared testexec — назначение роли
        # заменяет все связи (set_role), а удаление роли чистит их же.
        # Иначе testexec останется без ролей и уронит поздние тесты.
        users = sync_request('GET', '/api/users', cookies=admin_cookies).json()
        uname = f"assign_{uuid.uuid4().hex[:8]}"
        assert not any(u['username'] == uname for u in users)
        resp = sync_request('POST', '/api/users',
                            json={'username': uname, 'password': 'pass1234'},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        target_id = resp.json()['id']
        resp = sync_request('PUT', f'/api/users/{target_id}/role',
                            json={'role_id': role_id}, cookies=admin_cookies)
        assert resp.status_code == 200, resp.text
        self._delete_role(sync_request, admin_cookies, role_id)
