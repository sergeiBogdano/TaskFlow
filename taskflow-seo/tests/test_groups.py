"""Ф5: глобальные группы пользователей (только superadmin)."""

import pytest


class TestGroups:

    @staticmethod
    def _login(sync_request, username, password):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': username, 'password': password})
        assert resp.status_code == 200, resp.text
        return {'taskflow_user': resp.cookies.get('taskflow_user')}

    def test_group_crud_requires_superadmin(self, sync_request, executor_cookies):
        resp = sync_request('GET', '/api/groups', cookies=executor_cookies)
        assert resp.status_code in (403, 401)
        resp = sync_request('POST', '/api/groups',
                            json={'name': 'forbidden_group', 'permissions': {'notes': True}},
                            cookies=executor_cookies)
        assert resp.status_code in (403, 401)

    def test_superuser_group_crud(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/groups',
                            json={'name': 'testers_group', 'permissions': {'reports': True}},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        group_id = resp.json()['id']

        resp = sync_request('GET', '/api/groups', cookies=admin_cookies)
        assert resp.status_code == 200
        assert any(g['id'] == group_id for g in resp.json())

        resp = sync_request('PUT', f'/api/groups/{group_id}',
                            json={'permissions': {'reports': True, 'modules': True}},
                            cookies=admin_cookies)
        assert resp.status_code == 200

        resp = sync_request('DELETE', f'/api/groups/{group_id}', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_group_permissions_add_to_role(self, sync_request, admin_cookies):
        """Права группы additive: пользователь получает право, которого нет у роли."""
        # роль без 'reports': executor
        resp = sync_request('POST', '/api/groups',
                            json={'name': 'group_grants_reports', 'permissions': {'reports': True}},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        group_id = resp.json()['id']

        # пользователь с ролью executor (без reports)
        users = sync_request('GET', '/api/users', cookies=admin_cookies).json()
        target = next(u for u in users if u['username'] == 'testexec')

        resp = sync_request('PUT', f'/api/groups/{group_id}/members',
                            json={'user_ids': [target['id']]}, cookies=admin_cookies)
        assert resp.status_code == 200

        # логин: permissions в /me теперь включают право группы
        cookies = self._login(sync_request, 'testexec', 'testpass')
        resp = sync_request('GET', '/api/auth/me', cookies=cookies)
        assert resp.status_code == 200
        assert resp.json()['user']['permissions'].get('reports') is True

        # и API, завязанное на право, открывается (отчёты у executor раньше были без)
        resp = sync_request('GET', '/api/reports', cookies=cookies)
        assert resp.status_code == 200

        # членство снимается — права возвращаются к роли
        resp = sync_request('PUT', f'/api/groups/{group_id}/members',
                            json={'user_ids': []}, cookies=admin_cookies)
        assert resp.status_code == 200
        resp = sync_request('GET', '/api/auth/me', cookies=cookies)
        assert not resp.json()['user']['permissions'].get('reports')

        resp = sync_request('DELETE', f'/api/groups/{group_id}', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_non_superadmin_cannot_manage_members(self, sync_request, admin_cookies, executor_cookies):
        resp = sync_request('POST', '/api/groups',
                            json={'name': 'group_members_guard', 'permissions': {}},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        group_id = resp.json()['id']

        resp = sync_request('PUT', f'/api/groups/{group_id}/members',
                            json={'user_ids': [1]}, cookies=executor_cookies)
        assert resp.status_code in (403, 401)

        resp = sync_request('DELETE', f'/api/groups/{group_id}', cookies=executor_cookies)
        assert resp.status_code in (403, 401)

        sync_request('DELETE', f'/api/groups/{group_id}', cookies=admin_cookies)
