import pytest


class TestDashboard:

    def test_dashboard_admin(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_dashboard_unauth(self, sync_request):
        resp = sync_request('GET', '/', cookies={})
        assert resp.status_code in (302, 307)

    def test_dashboard_stats(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/dashboard/stats', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert 'total' in data
        assert 'done' in data

    @pytest.mark.skip(reason='uses PostgreSQL-specific timezone() function')
    def test_dashboard_chart(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/dashboard/chart', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert 'labels' in data
        assert 'created' in data

    def test_dashboard_focus(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/dashboard/focus', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_dashboard_organizations(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/dashboard/organizations', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert 'items' in data
        assert 'scope' in data

    def test_dashboard_client_summaries(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/dashboard/client-summaries', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_dashboard_expiring(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/dashboard/expiring', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestNotifications:

    def test_api_notifications(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/notifications', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert 'notifications' in data
        assert 'unread_count' in data

    def test_unread_count(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/notifications/unread-count', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'count' in resp.json()

    def test_read_all(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/notifications/read-all', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True


class TestActivity:

    def test_api_activity(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/activity', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestSearch:

    def test_search(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/search?q=test', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_search_empty(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/search?q=', cookies=admin_cookies)
        assert resp.status_code == 200


class TestTemplates:

    def test_get_templates(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/templates', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


class TestSettings:

    def test_settings_page(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/settings', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_settings_save(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/settings',
                           data={'timezone': 'Europe/Moscow', 'theme': 'dark'},
                           cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert '/settings' in resp.headers['location']


class TestReports:

    def test_reports_page(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/reports', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_reports_data(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/reports/data', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_reports_list_api(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/reports', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestFiles:

    def test_file_upload_and_download(self, sync_request, admin_cookies):
        sync_request('POST', '/api/tasks',
                   json={'title': 'File Upload Task'},
                   cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'File Upload Task'), None)
        assert task is not None
        resp = sync_request('POST', f'/api/tasks/{task["id"]}/upload',
                          files={'file': ('test.txt', b'hello pytest', 'text/plain')},
                          cookies=admin_cookies)
        assert resp.status_code == 200
        file_id = resp.json()['id']
        resp2 = sync_request('GET', f'/api/files/{file_id}/download',
                            cookies=admin_cookies)
        assert resp2.status_code == 200
        assert resp2.content == b'hello pytest'

    def test_file_list(self, sync_request, admin_cookies):
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        tasks = r.json()
        if not tasks:
            sync_request('POST', '/api/tasks',
                        json={'title': 'List Files Task'},
                        cookies=admin_cookies)
            r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
            tasks = r.json()
        tid = tasks[0]['id']
        resp = sync_request('GET', f'/api/tasks/{tid}/files',
                          cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestSSE:

    def test_sse_endpoint_unauthorized(self):
        import asyncio
        from httpx import AsyncClient, ASGITransport
        from app.web.app import app

        async def _check():
            async with AsyncClient(transport=ASGITransport(app=app),
                                  base_url='http://test', timeout=3.0) as ac:
                resp = await ac.get('/api/sse')
                return resp.status_code

        loop = asyncio.new_event_loop()
        try:
            status = loop.run_until_complete(_check())
        finally:
            loop.close()
        assert status == 401


class TestExport:

    def test_csv_export(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/tasks/export/csv', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'text/csv' in resp.headers.get('content-type', '')

    def test_pdf_export(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/tasks/export/pdf', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'text/html' in resp.headers.get('content-type', '')

    def test_reports_csv_export(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/reports/export/csv', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'text/csv' in resp.headers.get('content-type', '')


class TestAdditionalAPI:

    def test_task_done_api(self, sync_request, admin_cookies):
        sync_request('POST', '/api/tasks',
                   json={'title': 'Done Test'},
                   cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'Done Test'), None)
        assert task is not None
        resp = sync_request('POST', f'/tasks/{task["id"]}/done',
                          cookies=admin_cookies)
        assert resp.status_code in (200, 302)

    def test_task_generate_next_api(self, sync_request, admin_cookies):
        sync_request('POST', '/api/tasks',
                   json={'title': 'Recurring Task'},
                   cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'Recurring Task'), None)
        assert task is not None
        resp = sync_request('POST', f'/api/tasks/{task["id"]}/generate-next',
                          cookies=admin_cookies)
        assert resp.status_code == 200

    def test_client_trash_list(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/clients/trash', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_client_contract_check(self, sync_request, admin_cookies):
        sync_request('POST', '/api/clients',
                   json={'org_name': 'Contract Check', 'status': 'active',
                        'contract_start': '2026-01-01',
                        'contract_end': '2027-12-31'},
                   cookies=admin_cookies)
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        c = next((c for c in r.json() if c['org_name'] == 'Contract Check'), None)
        assert c is not None
        resp = sync_request('GET', f'/api/clients/{c["id"]}/contract-check',
                          cookies=admin_cookies)
        assert resp.status_code == 200

    def test_client_health(self, sync_request, admin_cookies):
        sync_request('POST', '/api/clients',
                   json={'org_name': 'Health Check', 'status': 'active',
                        'contract_start': '2026-01-01',
                        'contract_end': '2027-12-31'},
                   cookies=admin_cookies)
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        c = next((c for c in r.json() if c['org_name'] == 'Health Check'), None)
        assert c is not None
        resp = sync_request('GET', f'/api/clients/{c["id"]}/health',
                          cookies=admin_cookies)
        assert resp.status_code == 200

    def test_client_bulk_action(self, sync_request, admin_cookies):
        sync_request('POST', '/api/clients',
                   json={'org_name': 'Bulk Test A', 'status': 'active',
                        'contract_start': '2026-01-01',
                        'contract_end': '2027-12-31'},
                   cookies=admin_cookies)
        sync_request('POST', '/api/clients',
                   json={'org_name': 'Bulk Test B', 'status': 'active',
                        'contract_start': '2026-01-01',
                        'contract_end': '2027-12-31'},
                   cookies=admin_cookies)
        r = sync_request('GET', '/api/clients', cookies=admin_cookies)
        ids = [c['id'] for c in r.json() if c['org_name'] in ('Bulk Test A', 'Bulk Test B')]
        resp = sync_request('POST', '/api/clients/bulk',
                          json={'ids': ids, 'action': 'delete'},
                          cookies=admin_cookies)
        assert resp.status_code == 200

    def test_calendar_tasks(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/calendar', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_tasks_trash_list(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/tasks/trash', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_user_list(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/users', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        admin = next((u for u in data if u.get('username') == 'admin'), None)
        assert admin is not None

    def test_user_create(self, sync_request, admin_cookies):
        resp = sync_request('POST', '/api/users',
                          json={'username': 'newuser_test',
                               'password': 'TestPass123',
                               'email': 'test@example.com'},
                          cookies=admin_cookies)
        assert resp.status_code in (200, 201, 400, 409)

    def test_role_list(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/roles', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_module_list(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/modules', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_reports_trash(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/reports/trash', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_notification_dismiss(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/notifications', cookies=admin_cookies)
        assert resp.status_code == 200
        notifs = resp.json()['notifications']
        if notifs:
            nid = notifs[0]['id']
            resp = sync_request('POST', f'/api/notifications/{nid}/dismiss',
                              cookies=admin_cookies)
            assert resp.status_code == 200

    def test_notification_delete(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/notifications', cookies=admin_cookies)
        notifs = resp.json()['notifications']
        if notifs:
            nid = notifs[0]['id']
            resp = sync_request('DELETE', f'/api/notifications/{nid}',
                              cookies=admin_cookies)
            assert resp.status_code in (200, 204)

    def test_search_with_params(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/search?q=task&type=task',
                          cookies=admin_cookies)
        assert resp.status_code == 200

    def test_quick_tasks_list(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/quick-tasks', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_saved_views_list(self, sync_request, admin_cookies):
        resp = sync_request('GET', '/api/saved-views', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_task_batch_api(self, sync_request, admin_cookies):
        sync_request('POST', '/api/tasks',
                   json={'title': 'Batch API Task'},
                   cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'Batch API Task'), None)
        assert task is not None
        resp = sync_request('POST', '/api/tasks/batch',
                          json={'ids': [task['id']], 'action': 'start', 'value': None},
                          cookies=admin_cookies)
        assert resp.status_code == 200
