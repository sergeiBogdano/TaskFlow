"""Ф7: кастомные роли окружения — выдача/снятие, потолок, кран."""

import uuid


class TestWsRoles:

    @staticmethod
    def _login(sync_request, username, password):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': username, 'password': password})
        assert resp.status_code == 200, resp.text
        return {'taskflow_user': resp.cookies.get('taskflow_user')}

    @staticmethod
    def _make_ws(sync_request, cookies):
        name = f'ws_roles_{uuid.uuid4().hex[:8]}'
        resp = sync_request('POST', '/api/workspaces',
                            json={'name': name}, cookies=cookies)
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def _make_user(sync_request, admin_cookies, username):
        resp = sync_request('POST', '/api/users',
                            json={'username': username, 'password': 'pass1234'},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        uid = resp.json()['id']
        cookies = TestWsRoles._login(sync_request, username, 'pass1234')
        return uid, cookies

    @staticmethod
    def _create_role(sync_request, cookies, ws_id, name, permissions):
        return sync_request('POST', f'/api/workspaces/{ws_id}/roles',
                            json={'name': name, 'permissions': permissions},
                            cookies=cookies)

    def test_crud_and_assignment(self, sync_request, admin_cookies):
        """Создание роли, назначение участнику, снятие, удаление."""
        ws = self._make_ws(sync_request, admin_cookies)
        uid, member_cookies = self._make_user(
            sync_request, admin_cookies, f'wsrole_{uuid.uuid4().hex[:8]}')
        resp = sync_request('POST', f"/api/workspaces/{ws['id']}/members",
                            json={'user_id': uid, 'role': 'member'},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text

        # создание
        resp = self._create_role(sync_request, admin_cookies, ws['id'],
                                 'Трафик-менеджер', {'tasks': True, 'reports': True})
        assert resp.status_code == 201, resp.text
        role_id = resp.json()['id']
        assert resp.json()['permissions'] == {'tasks': True, 'reports': True}

        # список
        resp = sync_request('GET', f"/api/workspaces/{ws['id']}/roles",
                            cookies=admin_cookies)
        assert resp.status_code == 200
        assert any(r['id'] == role_id for r in resp.json()['roles'])
        assert resp.json()['features'].get('tasks') is not False

        # дубликат названия
        resp = self._create_role(sync_request, admin_cookies, ws['id'],
                                 'Трафик-менеджер', {'tasks': True})
        assert resp.status_code == 400

        # назначение участнику
        resp = sync_request('PUT',
                            f"/api/workspaces/{ws['id']}/members/{uid}/custom-role",
                            json={'role_id': role_id}, cookies=admin_cookies)
        assert resp.status_code == 200, resp.text
        assert resp.json()['custom_role_id'] == role_id

        resp = sync_request('GET', f"/api/workspaces/{ws['id']}/members",
                            cookies=admin_cookies)
        row = next(m for m in resp.json() if m['user_id'] == uid)
        assert row['custom_role_id'] == role_id
        assert row['custom_role'] == 'Трафик-менеджер'
        assert row['role'] == 'member'  # базовый rank сохраняется

        # снятие
        resp = sync_request('PUT',
                            f"/api/workspaces/{ws['id']}/members/{uid}/custom-role",
                            json={'role_id': None}, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['custom_role_id'] is None

        # обновление роли
        resp = sync_request('PUT', f"/api/workspaces/{ws['id']}/roles/{role_id}",
                            json={'permissions': {'tasks': True}},
                            cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['permissions'] == {'tasks': True}

        # удаление
        resp = sync_request('DELETE', f"/api/workspaces/{ws['id']}/roles/{role_id}",
                            cookies=admin_cookies)
        assert resp.status_code == 200
        resp = sync_request('GET', f"/api/workspaces/{ws['id']}/roles",
                            cookies=admin_cookies)
        assert all(r['id'] != role_id for r in resp.json()['roles'])

    def test_scope_work_and_validation(self, sync_request, admin_cookies):
        """Только scope=work-ключи, пустое имя и неизвестный ключ — 400."""
        ws = self._make_ws(sync_request, admin_cookies)
        # app-scope ключ
        resp = self._create_role(sync_request, admin_cookies, ws['id'],
                                 'Системная', {'users': True})
        assert resp.status_code == 400, resp.text
        # неизвестный ключ
        resp = self._create_role(sync_request, admin_cookies, ws['id'],
                                 'Мусорная', {'no_such_key': True})
        assert resp.status_code == 400
        # пустое имя
        resp = self._create_role(sync_request, admin_cookies, ws['id'],
                                 '   ', {'tasks': True})
        assert resp.status_code == 400

    def test_member_cannot_manage_roles(self, sync_request, admin_cookies, executor_cookies):
        """Роли окружения видит и правит только owner/admin."""
        ws = self._make_ws(sync_request, admin_cookies)
        resp = sync_request('GET', f"/api/workspaces/{ws['id']}/roles",
                            cookies=executor_cookies)
        assert resp.status_code == 403
        resp = self._create_role(sync_request, executor_cookies, ws['id'],
                                 'Своя', {'tasks': True})
        assert resp.status_code == 403

    def test_ceiling_blocks_outranked_grant(self, sync_request, admin_cookies, executor_cookies):
        """Потолок: выдать можно только то, что есть в app-правах или в
        effective-правах этого окружения (union). Чего нет нигде — 403."""
        ws = self._make_ws(sync_request, admin_cookies)
        # executor уже admin этого окружения
        users = sync_request('GET', '/api/users', cookies=admin_cookies).json()
        exec_id = next(u['id'] for u in users if u['username'] == 'testexec')
        resp = sync_request('POST', f"/api/workspaces/{ws['id']}/members",
                            json={'user_id': exec_id, 'role': 'admin'},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text

        # users_password_reset нет ни в app executor, ни в rank-defaults → потолок
        resp = self._create_role(sync_request, executor_cookies, ws['id'],
                                 'Сброс', {'users_password_reset': True})
        assert resp.status_code == 403, resp.text
        assert 'users_password_reset' in resp.text

        # reports в effective-правах админа окружения есть → делегирование разрешено
        resp = self._create_role(sync_request, executor_cookies, ws['id'],
                                 'Делегат', {'reports': True})
        assert resp.status_code == 201, resp.text
        delegated_id = resp.json()['id']
        sync_request('DELETE', f"/api/workspaces/{ws['id']}/roles/{delegated_id}",
                     cookies=admin_cookies)

        # superadmin (все права) — потолок не мешает
        resp = self._create_role(sync_request, admin_cookies, ws['id'],
                                 'Выше потолка', {'reports': True})
        assert resp.status_code == 201, resp.text

    def test_feature_switch_blocks_grant(self, sync_request, admin_cookies):
        """Кран закрыт: чекбокс скрыт (features=false) и выдать нельзя."""
        ws = self._make_ws(sync_request, admin_cookies)

        def set_feature(enabled):
            resp = sync_request('PUT', '/api/features', json={
                'scope': 'global', 'key': 'reports', 'enabled': enabled,
            }, cookies=admin_cookies)
            assert resp.status_code == 200, resp.text

        set_feature(False)
        try:
            # выдать нельзя
            resp = self._create_role(sync_request, admin_cookies, ws['id'],
                                     'С отключённой', {'reports': True})
            assert resp.status_code == 403, resp.text
            assert 'reports' in resp.text
            # чекбокса нет: эффективное состояние false
            resp = sync_request('GET', f"/api/workspaces/{ws['id']}/roles",
                                cookies=admin_cookies)
            assert resp.status_code == 200
            assert resp.json()['features'].get('reports') is False
            # а без неё — можно
            resp = self._create_role(sync_request, admin_cookies, ws['id'],
                                     'Без неё', {'tasks': True})
            assert resp.status_code == 201, resp.text
        finally:
            set_feature(True)

    def test_default_workspace_rights(self):
        """owner/admin → полный набор «Работы» (кроме users_password_reset —
        он opt-in, иначе invite-then-reset), member → только базовые."""
        from app.core.permission_catalog import (
            workspace_default_permissions,
            work_scope_keys,
        )

        all_work = set(work_scope_keys())
        owner = set(workspace_default_permissions('owner'))
        admin = set(workspace_default_permissions('admin'))
        member = set(workspace_default_permissions('member'))

        assert owner == all_work - {'users_password_reset'}
        assert admin == all_work - {'users_password_reset'}
        assert member < all_work
        assert 'users_password_reset' not in member
        assert member < all_work
        # базовые (level=basic) у участника есть, расширения — нет
        assert {'dashboard', 'tasks', 'kanban', 'calendar', 'clients'} <= member
        assert 'reports' not in member
        assert 'client_tab_access' not in member
        assert 'tasks_view_others' not in member
