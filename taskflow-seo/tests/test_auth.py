import pytest


class TestAuth:

    def test_login_rejects_form_body(self, sync_request):
        resp = sync_request('POST', '/api/auth/login', data={'username': '4dmin', 'password': '4dmin'})
        assert resp.status_code == 422

    def test_login_success(self, sync_request, client):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': '4dmin', 'password': '4dmin'})
        assert resp.status_code == 200
        data = resp.json()
        assert 'user' in data
        assert 'token' not in data
        assert data['user']['username'] == '4dmin'

    def test_login_wrong_password(self, sync_request, client):
        resp = sync_request('POST', '/api/auth/login',
                            json={'username': '4dmin', 'password': 'wrong'})
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
        assert resp.json()['user']['username'] == '4dmin'

    def test_get_me_unauthenticated(self, sync_request, client):
        resp = sync_request('GET', '/api/auth/me')
        assert resp.status_code == 401

    def test_get_me_invalid_token(self, sync_request, client):
        resp = sync_request('GET', '/api/auth/me',
                            cookies={'taskflow_user': 'invalid-token'})
        assert resp.status_code == 401

    def test_dashboard_requires_auth(self, sync_request, client):
        assert sync_request('GET', '/api/dashboard/focus', cookies={}).status_code == 401

    def test_login_cookie_security(self, sync_request, client):
        resp = sync_request('POST', '/api/auth/login', json={'username': '4dmin', 'password': '4dmin'})
        assert resp.status_code == 200
        cookie = resp.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=lax' in cookie
        assert resp.cookies.get('taskflow_user')
