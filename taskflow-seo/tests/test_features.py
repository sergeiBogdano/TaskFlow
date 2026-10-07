"""Ф6: кран доступности функций (FeatureOverride + приоритет user > workspace > group > global)."""

import pytest


class TestFeatures:

    @staticmethod
    def _login(sync_request, username, password):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': username, 'password': password})
        assert resp.status_code == 200, resp.text
        return {'taskflow_user': resp.json() and resp.cookies.get('taskflow_user')}

    @staticmethod
    def _set(sync_request, cookies, **payload):
        return sync_request('PUT', '/api/features', json=payload, cookies=cookies)

    @staticmethod
    def _reset(sync_request, cookies, key, enabled=True, scope='global', target_id=None):
        resp = sync_request('PUT', '/api/features', json={
            'scope': scope, 'target_id': target_id, 'key': key, 'enabled': enabled,
        }, cookies=cookies)
        assert resp.status_code == 200, resp.text

    def test_features_restricted_to_superadmin(self, sync_request, executor_cookies):
        resp = sync_request('GET', '/api/features', cookies=executor_cookies)
        assert resp.status_code in (403, 401)
        resp = self._set(sync_request, executor_cookies,
                         scope='global', key='reports', enabled=False)
        assert resp.status_code in (403, 401)

    def test_root_can_disable_feature_without_locking_itself_out(self, sync_request, admin_cookies):
        """Root отключает функцию для остальных, но сам сохраняет аварийный доступ."""
        # baseline: список ролей доступен (право users включено)
        resp = sync_request('GET', '/api/roles', cookies=admin_cookies)
        assert resp.status_code == 200, resp.text

        self._reset(sync_request, admin_cookies, 'users', enabled=False)
        try:
            resp = sync_request('GET', '/api/roles', cookies=admin_cookies)
            assert resp.status_code == 200, resp.text

            # /me отдаёт карту доступности: users = false
            resp = sync_request('GET', '/api/auth/me', cookies=admin_cookies)
            assert resp.status_code == 200
            assert resp.json()['user']['features'].get('users') is False
        finally:
            self._reset(sync_request, admin_cookies, 'users', enabled=True)

        resp = sync_request('GET', '/api/roles', cookies=admin_cookies)
        assert resp.status_code == 200, resp.text
        resp = sync_request('GET', '/api/auth/me', cookies=admin_cookies)
        assert resp.json()['user']['features'].get('users') is True

    def test_settings_key_cannot_be_switched_off(self, sync_request, admin_cookies):
        resp = self._set(sync_request, admin_cookies, scope='global', key='settings', enabled=False)
        assert resp.status_code == 400, resp.text

    def test_unknown_feature_and_scope_rejected(self, sync_request, admin_cookies):
        resp = self._set(sync_request, admin_cookies, scope='global', key='no_such_key', enabled=False)
        assert resp.status_code == 400
        resp = self._set(sync_request, admin_cookies, scope='galaxy', key='reports', enabled=False)
        assert resp.status_code == 400

    def test_grant_blocked_while_feature_off(self, sync_request, admin_cookies):
        """Выдать право отключённой функции нельзя: 403 в ролях и группах."""
        self._reset(sync_request, admin_cookies, 'reports', enabled=False)
        try:
            resp = sync_request('POST', '/api/roles',
                                json={'name': 'role_blocked_feature', 'permissions': {'reports': True}},
                                cookies=admin_cookies)
            assert resp.status_code == 403, resp.text
            assert 'reports' in resp.text

            resp = sync_request('POST', '/api/groups',
                                json={'name': 'group_blocked_feature', 'permissions': {'reports': True}},
                                cookies=admin_cookies)
            assert resp.status_code == 403, resp.text
        finally:
            self._reset(sync_request, admin_cookies, 'reports', enabled=True)

        # после включения крана выдача снова проходит
        resp = sync_request('POST', '/api/roles',
                            json={'name': 'role_after_restore', 'permissions': {'reports': True}},
                            cookies=admin_cookies)
        assert resp.status_code == 201, resp.text
        role_id = resp.json()['id']
        sync_request('DELETE', f'/api/roles/{role_id}', cookies=admin_cookies)

    def test_user_override_beats_global(self, sync_request, admin_cookies, executor_cookies):
        """Приоритет: user > global. Глобально выключено, пользователю включено."""
        users = sync_request('GET', '/api/users', cookies=admin_cookies).json()
        target = next(u for u in users if u['username'] == 'testexec')

        # снимаем возможный пользовательский переключатель, оставшийся от прошлых прогонов
        self._reset(sync_request, admin_cookies, 'reports', enabled=None,
                    scope='user', target_id=target['id'])
        self._reset(sync_request, admin_cookies, 'reports', enabled=False)
        try:
            cookies = self._login(sync_request, 'testexec', 'testpass')
            resp = sync_request('GET', '/api/auth/me', cookies=cookies)
            assert resp.json()['user']['features'].get('reports') is False

            self._reset(sync_request, admin_cookies, 'reports', enabled=True,
                        scope='user', target_id=target['id'])
            resp = sync_request('GET', '/api/auth/me', cookies=cookies)
            assert resp.json()['user']['features'].get('reports') is True
        finally:
            self._reset(sync_request, admin_cookies, 'reports', enabled=None,
                        scope='user', target_id=target['id'])
            self._reset(sync_request, admin_cookies, 'reports', enabled=True)

    def test_effective_features_returned_by_endpoint(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/features', cookies=admin_cookies)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data['effective'], dict) and data['effective']
        assert isinstance(data['overrides'], list)
        assert any(g['scope'] in ('app', 'work') for g in data['catalog'])
