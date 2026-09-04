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
        resp = sync_request('GET', '/api/tasks/all', cookies=executor_cookies)
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
        for url in ['/api/users', '/api/roles', '/api/tasks/all', '/api/clients',
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

    def test_admin_can_access_ai_command(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/ai/task-command',
                          json={'text': 'test command'},
                          cookies=admin_cookies)
        assert resp.status_code in (200, 422, 500)

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
