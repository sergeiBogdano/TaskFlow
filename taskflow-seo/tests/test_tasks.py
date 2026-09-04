import pytest


class TestTasks:

    def test_tasks_page(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/tasks', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_api_tasks_list(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/api/tasks', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_api_tasks_all(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_task_create_form(self, sync_request, client, admin_cookies):
        resp = sync_request('POST', '/tasks/create',
                           data={'title': 'New Task', 'status': 'todo'},
                           cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert '/tasks' in resp.headers['location']

    def test_task_create_api(self, sync_request, client, admin_cookies):
        resp = sync_request('POST', '/api/tasks',
                           json={'title': 'API Task', 'priority': 'high'},
                           cookies=admin_cookies)
        assert resp.status_code == 201
        data = resp.json()
        assert data['title'] == 'API Task'

    def test_task_edit(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'Edit Test', 'priority': 'medium'},
                    cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'Edit Test'), None)
        assert task is not None
        tid = task['id']
        resp = sync_request('PUT', f'/api/tasks/{tid}',
                           json={'title': 'Edited Task', 'priority': 'high'},
                           cookies=admin_cookies)
        assert resp.status_code == 200

    def test_task_move_api(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'Move Test', 'priority': 'medium'},
                    cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'Move Test'), None)
        assert task is not None
        resp = sync_request('POST', f'/api/tasks/{task["id"]}/move',
                           json={'status': 'done'}, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_task_start_api(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'Start Test', 'priority': 'medium'},
                    cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'Start Test'), None)
        assert task is not None
        resp = sync_request('POST', f'/api/tasks/{task["id"]}/start',
                           cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_task_batch_update(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'Batch 1'}, cookies=admin_cookies)
        sync_request('POST', '/api/tasks',
                    json={'title': 'Batch 2'}, cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        ids = [t['id'] for t in r.json() if t['title'] in ('Batch 1', 'Batch 2')]
        resp = sync_request('POST', '/api/tasks/bulk',
                           json={'ids': ids, 'fields': {'priority': 'high'}},
                           cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True



    def test_kanban_page(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/kanban', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_calendar_page(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/calendar', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_task_get_api(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'Get API Task'},
                    cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'Get API Task'), None)
        assert task is not None
        resp = sync_request('GET', f'/api/tasks/{task["id"]}',
                          cookies=admin_cookies)
        assert resp.status_code == 200

    def test_task_not_found_404(self, sync_request, client, admin_cookies):
        resp = sync_request('GET', '/api/tasks/99999',
                          cookies=admin_cookies)
        assert resp.status_code == 404

    def test_task_delete_and_restore_api(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'Delete Test'},
                    cookies=admin_cookies)
        r = sync_request('GET', '/api/tasks/all', cookies=admin_cookies)
        task = next((t for t in r.json() if t['title'] == 'Delete Test'), None)
        assert task is not None
        tid = task['id']
        resp = sync_request('DELETE', f'/api/tasks/{tid}',
                          cookies=admin_cookies)
        assert resp.status_code == 200
        resp = sync_request('POST', f'/api/tasks/{tid}/restore',
                          cookies=admin_cookies)
        assert resp.status_code == 200

    def test_task_priority_filter(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'High Task', 'priority': 'high'},
                    cookies=admin_cookies)
        resp = sync_request('GET', '/api/tasks?priority=high',
                          cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_task_status_filter(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'Status Task'},
                    cookies=admin_cookies)
        resp = sync_request('GET', '/api/tasks?status=todo',
                          cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_task_search(self, sync_request, client, admin_cookies):
        sync_request('POST', '/api/tasks',
                    json={'title': 'Searchable Unique Title'},
                    cookies=admin_cookies)
        resp = sync_request('GET', '/api/tasks?search=Searchable',
                          cookies=admin_cookies)
        assert resp.status_code == 200
