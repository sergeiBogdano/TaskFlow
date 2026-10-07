"""Ф8: effective-права окружения.

Окружение заменяет app-права на scope=work: точный набор кастомной роли,
иначе база ранга. Закрытый раздел API → 403, выключенная краном
функция → 403.
"""

import uuid


class TestWorkspacePermissions:

    @staticmethod
    def _login(sync_request, username, password):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': username, 'password': password})
        assert resp.status_code == 200, resp.text
        return {'taskflow_user': resp.cookies.get('taskflow_user')}

    @staticmethod
    def _make_ws(sync_request, cookies, name=None):
        resp = sync_request('POST', '/api/workspaces',
                            json={'name': name or f'wsperm_{uuid.uuid4().hex[:8]}'},
                            cookies=cookies)
        assert resp.status_code == 201, resp.text
        return resp.json()

    @staticmethod
    def _me(sync_request, cookies, workspace_id=None):
        url = '/api/auth/me'
        if workspace_id is not None:
            url += f'?workspace_id={workspace_id}'
        resp = sync_request('GET', url, cookies=cookies)
        assert resp.status_code == 200, resp.text
        return resp.json()['user']['permissions']

    @staticmethod
    def _create_user(sync_request, admin_cookies, username, role_name=None):
        resp = sync_request('POST', '/api/users',
                            json={'username': username, 'password': 'pass1234'},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        uid = resp.json()['id']
        if role_name:
            roles = sync_request('GET', '/api/roles', cookies=admin_cookies).json()
            role_id = next(r['id'] for r in roles if r['name'] == role_name)
            resp = sync_request('PUT', f'/api/users/{uid}/role',
                                json={'role_id': role_id}, cookies=admin_cookies)
            assert resp.status_code == 200, resp.text
        return uid

    @staticmethod
    def _add_member(sync_request, admin_cookies, ws_id, user_id, role='member'):
        resp = sync_request('POST', f'/api/workspaces/{ws_id}/members',
                            json={'user_id': user_id, 'role': role},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text

    def test_workspace_replaces_app_work_permissions(self, sync_request, admin_cookies):
        """manager (app-права есть) в окружении как member → work-права окружения."""
        username = f'wsperm_{uuid.uuid4().hex[:8]}'
        uid = self._create_user(sync_request, admin_cookies, username, role_name='manager')
        cookies = self._login(sync_request, username, 'pass1234')

        # без окружения работают app-права (в роли manager есть «Отчёты»)
        assert self._me(sync_request, cookies).get('reports') is True

        ws = self._make_ws(sync_request, admin_cookies)
        self._add_member(sync_request, admin_cookies, ws['id'], uid, role='member')

        # в окружении действуют права участника: расширений нет
        perms = self._me(sync_request, cookies, workspace_id=ws['id'])
        assert not perms.get('reports')
        assert perms.get('tasks') is True  # базовые права есть

        # API закрыт для этого окружения…
        resp = sync_request('GET', f'/api/reports/data?workspace_id={ws["id"]}',
                            cookies=cookies)
        assert resp.status_code == 403, resp.text
        # …а без указания окружения остаются app-права
        resp = sync_request('GET', '/api/reports/data', cookies=cookies)
        assert resp.status_code == 200, resp.text

        # кастомная роль окружения возвращает право
        resp = sync_request('POST', f'/api/workspaces/{ws["id"]}/roles',
                            json={'name': 'Отчётчик', 'permissions': {'reports': True}},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        role_id = resp.json()['id']
        resp = sync_request('PUT',
                            f'/api/workspaces/{ws["id"]}/members/{uid}/custom-role',
                            json={'role_id': role_id}, cookies=admin_cookies)
        assert resp.status_code == 200, resp.text

        perms = self._me(sync_request, cookies, workspace_id=ws['id'])
        assert perms.get('reports') is True
        resp = sync_request('GET', f'/api/reports/data?workspace_id={ws["id"]}',
                            cookies=cookies)
        assert resp.status_code == 200, resp.text

    def test_owner_gets_full_work_set(self, sync_request, admin_cookies):
        """Владелец окружения получает полный набор «Работы», даже если app-роль беднее."""
        # свежий пользователь с app-ролью executor (без «Отчётов»), а не session-fixture:
        # testexec накапливает окружения в персистентной test.db и упирается в лимит 3
        username = f'ownfull_{uuid.uuid4().hex[:8]}'
        self._create_user(sync_request, admin_cookies, username, role_name='executor')
        cookies = self._login(sync_request, username, 'pass1234')

        own_ws = self._make_ws(sync_request, cookies, name=f'own_{uuid.uuid4().hex[:6]}')
        resp = sync_request('GET', f'/api/reports/data?workspace_id={own_ws["id"]}',
                            cookies=cookies)
        assert resp.status_code == 200, resp.text

        # а в чужом окружении, где он простой участник — только базовые права
        users = sync_request('GET', '/api/users', cookies=admin_cookies).json()
        uid = next(u['id'] for u in users if u['username'] == username)
        ws = self._make_ws(sync_request, admin_cookies)
        self._add_member(sync_request, admin_cookies, ws['id'], uid, role='member')
        resp = sync_request('GET', f'/api/reports/data?workspace_id={ws["id"]}',
                            cookies=cookies)
        assert resp.status_code == 403, resp.text

    def test_member_cannot_manage_workspace(self, sync_request, admin_cookies):
        """Управление окружением закрыто правом «workspace» (member его не имеет)."""
        username = f'wsmgmt_{uuid.uuid4().hex[:8]}'
        uid = self._create_user(sync_request, admin_cookies, username, role_name='manager')
        cookies = self._login(sync_request, username, 'pass1234')
        ws = self._make_ws(sync_request, admin_cookies)
        self._add_member(sync_request, admin_cookies, ws['id'], uid, role='member')

        # управление существующим окружением требует work-права «workspace»,
        # которого у member нет (создание своего окружения — отдельный случай)
        resp = sync_request('PATCH',
                            f'/api/workspaces/{ws["id"]}',
                            json={'name': 'не должно получиться'},
                            cookies=cookies)
        assert resp.status_code == 403, resp.text
        assert 'workspace' in resp.text

        # чтение списка окружений участнику открыто
        resp = sync_request('GET', '/api/workspaces', cookies=cookies)
        assert resp.status_code == 200, resp.text

    def test_closed_feature_blocks_work_api(self, sync_request, admin_cookies):
        """Кран: выключенная функция = 403 даже для суперадмина."""
        ws = self._make_ws(sync_request, admin_cookies)
        resp = sync_request('PUT', '/api/features', json={
            'scope': 'global', 'key': 'reports', 'enabled': False,
        }, cookies=admin_cookies)
        assert resp.status_code == 200, resp.text
        try:
            resp = sync_request('GET', f'/api/reports/data?workspace_id={ws["id"]}',
                                cookies=admin_cookies)
            assert resp.status_code == 403, resp.text
            assert 'отключена' in resp.text.lower() or 'reports' in resp.text
        finally:
            sync_request('PUT', '/api/features', json={
                'scope': 'global', 'key': 'reports', 'enabled': True,
            }, cookies=admin_cookies)
        resp = sync_request('GET', f'/api/reports/data?workspace_id={ws["id"]}',
                            cookies=admin_cookies)
        assert resp.status_code == 200, resp.text

    def test_sensitive_tab_respects_workspace_role(self, sync_request, admin_cookies):
        """Мелкие права внутри модуля (client_delete) тоже считаются по окружению."""
        username = f'wstabs_{uuid.uuid4().hex[:8]}'
        uid = self._create_user(sync_request, admin_cookies, username, role_name='admin')
        cookies = self._login(sync_request, username, 'pass1234')
        ws = self._make_ws(sync_request, admin_cookies)
        self._add_member(sync_request, admin_cookies, ws['id'], uid, role='member')

        # app-роль admin даёт client_delete, но в окружении он member → удаления нет
        resp = sync_request('POST', f'/api/clients?workspace_id={ws["id"]}',
                            json={'org_name': f'Клиент {uuid.uuid4().hex[:6]}',
                                  'domain': f'{uuid.uuid4().hex[:8]}.example.com'},
                            cookies=cookies)
        assert resp.status_code in (200, 201), resp.text
        client_id = resp.json().get('id') or resp.json().get('client_id')
        resp = sync_request('DELETE', f'/api/clients/{client_id}?workspace_id={ws["id"]}',
                            cookies=cookies)
        assert resp.status_code == 403, resp.text
        assert 'delete' in resp.text or 'клиент' in resp.text.lower()
