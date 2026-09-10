import pytest


class TestAuth:

    def test_login_page(self, sync_request):
        resp = sync_request('GET', '/login')
        assert resp.status_code in (200, 302)

    def test_login_success(self, sync_request, client):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': 'admin', 'password': 'admin'})
        assert resp.status_code == 200
        data = resp.json()
        assert 'user' in data
        assert 'token' in data
        assert data['user']['username'] == 'admin'

    def test_login_wrong_password(self, sync_request, client):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': 'admin', 'password': 'wrong'})
        assert resp.status_code == 401
        assert 'error' in resp.json()

    def test_login_nonexistent(self, sync_request, client):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': 'nobody', 'password': 'test'})
        assert resp.status_code == 401

    def test_login_missing_fields(self, sync_request, client):
        resp = sync_request('POST', '/api/auth/login', json={})
        assert resp.status_code == 422

    def test_login_empty_body(self, sync_request, client):
        resp = sync_request('POST', '/api/auth/login')
        assert resp.status_code == 422

    def test_logout(self, sync_request, client, admin_cookies):
        resp = sync_request('POST', '/api/auth/logout', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_get_me_authenticated(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/api/auth/me', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['user']['username'] == 'admin'

    def test_get_me_unauthenticated(self, sync_request, client):
        resp = sync_request('GET', '/api/auth/me')
        assert resp.status_code == 401

    def test_get_me_invalid_token(self, sync_request, client):
        resp = sync_request('GET', '/api/auth/me',
                            cookies={'taskflow_user': 'invalid-token'})
        assert resp.status_code == 401

    def test_dashboard_requires_auth(self, sync_request, client):
        resp = sync_request('GET', '/', cookies={})
        assert resp.status_code in (302, 307)
        assert '/login' in resp.headers['location']

    def test_login_form_legacy(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/login')
        assert resp.status_code == 200
