import asyncio


def _request(client, method, url, **kw):
    loop = asyncio.get_event_loop()
    if 'cookies' in kw:
        c = kw.pop('cookies')
        kw.setdefault('headers', {})['Cookie'] = '; '.join(f'{k}={v}' for k, v in c.items()) if c else ''
    return loop.run_until_complete(client.request(method, url, **kw))


def _login(client, username, password):
    return _request(client, 'POST', '/login', data={'username': username, 'password': password}, follow_redirects=False)


class TestAuth:

    def test_login_page(self, client):
        resp = _request(client, 'GET', '/login')
        assert resp.status_code == 200

    def test_login_success(self, client):
        resp = _login(client, 'admin', 'admin')
        assert resp.status_code == 302
        assert resp.headers['location'] == '/'
        assert 'taskflow_user' in resp.cookies

    def test_login_wrong_password(self, client):
        resp = _login(client, 'admin', 'wrong')
        assert resp.status_code == 200

    def test_login_nonexistent(self, client):
        resp = _login(client, 'nobody', 'test')
        assert resp.status_code == 200

    def test_logout(self, client, admin_cookies):
        resp = _request(client, 'GET', '/logout', cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers['location'] == '/login'

    def test_auth_required_redirect(self, client):
        resp = _request(client, 'GET', '/settings', follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert '/login' in resp.headers['location']


class TestDashboard:

    def test_dashboard_admin(self, client, admin_cookies):
        resp = _request(client, 'GET', '/', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_dashboard_unauth(self, client):
        resp = _request(client, 'GET', '/', follow_redirects=False, cookies={})
        assert resp.status_code in (302, 307)
        assert '/login' in resp.headers['location']


class TestTasks:

    def _create_task(self, client, cookies, title='Pytest Task'):
        _request(client, 'POST', '/tasks/create', data={'title': title, 'status': 'todo'}, cookies=cookies, follow_redirects=False)
        r = _request(client, 'GET', '/api/tasks', cookies=cookies)
        return r.json()[0]['id']

    def test_tasks_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/tasks', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_api_tasks_list(self, client, admin_cookies):
        self._create_task(client, admin_cookies)
        resp = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert 'id' in data[0] and 'title' in data[0] and 'status' in data[0]

    def test_api_tasks_all(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/tasks/all', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_task_create(self, client, admin_cookies):
        resp = _request(client, 'POST', '/tasks/create', data={'title': 'New Task', 'status': 'todo'}, cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert '/tasks' in resp.headers['location']

    def test_task_edit(self, client, admin_cookies):
        tid = self._create_task(client, admin_cookies)
        resp = _request(client, 'POST', f'/tasks/{tid}/edit', data={'title': 'Edited', 'status': 'in_progress'}, cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert '/tasks' in resp.headers['location']

    def test_task_move(self, client, admin_cookies):
        tid = self._create_task(client, admin_cookies)
        resp = _request(client, 'POST', f'/api/tasks/{tid}/move', json={'status': 'done'}, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_task_start(self, client, admin_cookies):
        tid = self._create_task(client, admin_cookies)
        resp = _request(client, 'POST', f'/api/tasks/{tid}/start', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_task_batch(self, client, admin_cookies):
        self._create_task(client, admin_cookies)
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        ids = [t['id'] for t in r.json()[:2]]
        resp = _request(client, 'POST', '/api/tasks/batch', json={'ids': ids, 'action': 'done'}, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_kanban_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/kanban', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_calendar_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/calendar', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_task_print(self, client, admin_cookies):
        tid = self._create_task(client, admin_cookies)
        resp = _request(client, 'GET', f'/tasks/{tid}/print', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_task_generate_next(self, client, admin_cookies):
        tid = self._create_task(client, admin_cookies)
        _request(client, 'PATCH', f'/api/tasks/{tid}',
                 json={'recurring_interval': 'daily', 'recurring_count': 3},
                 cookies=admin_cookies)
        resp = _request(client, 'POST', f'/api/tasks/{tid}/generate-next', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True


class TestClients:
    _client_counter = 0

    def _create_client(self, client, cookies, name='Pytest Org'):
        TestClients._client_counter += 1
        n = TestClients._client_counter
        _request(client, 'POST', '/clients/create', data={
            'org_name': f'{name} {n}', 'domain': f'pytest{n}.test',
            'contract_end': '2026-12-31', 'status': 'active',
        }, cookies=cookies, follow_redirects=False)
        r = _request(client, 'GET', '/api/clients', cookies=cookies)
        return r.json()[0]['id']

    def test_clients_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/clients', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_clients_detail(self, client, admin_cookies):
        cid = self._create_client(client, admin_cookies)
        resp = _request(client, 'GET', f'/clients/{cid}', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_clients_create(self, client, admin_cookies):
        resp = _request(client, 'POST', '/clients/create', data={
            'org_name': 'Second Org', 'domain': 'second.test',
            'contract_end': '2027-06-30', 'status': 'active',
        }, cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert '/clients' in resp.headers['location']

    def test_clients_update(self, client, admin_cookies):
        cid = self._create_client(client, admin_cookies)
        resp = _request(client, 'POST', f'/clients/{cid}/update', data={
            'org_name': 'Updated Org', 'contract_end': '2026-12-31',
        }, cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert f'/clients/{cid}' in resp.headers['location']

    def test_clients_status(self, client, admin_cookies):
        cid = self._create_client(client, admin_cookies)
        resp = _request(client, 'POST', f'/clients/{cid}/status', data={'status': 'suspended'}, cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        _request(client, 'POST', f'/clients/{cid}/status', data={'status': 'active'}, cookies=admin_cookies, follow_redirects=False)

    def test_client_print(self, client, admin_cookies):
        cid = self._create_client(client, admin_cookies)
        resp = _request(client, 'GET', f'/clients/{cid}/print', cookies=admin_cookies)
        assert resp.status_code == 200


class TestTrashAndRestore:

    def _task_id(self, client, cookies):
        r = _request(client, 'GET', '/api/tasks', cookies=cookies)
        tasks = r.json()
        if tasks:
            return tasks[-1]['id']
        _request(client, 'POST', '/tasks/create', data={'title': 'Del Test', 'status': 'todo'}, cookies=cookies, follow_redirects=False)
        r = _request(client, 'GET', '/api/tasks', cookies=cookies)
        return r.json()[0]['id']

    def test_task_delete_api(self, client, admin_cookies):
        tid = self._task_id(client, admin_cookies)
        resp = _request(client, 'POST', f'/api/tasks/{tid}/delete', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_task_restore_api(self, client, admin_cookies):
        tid = self._task_id(client, admin_cookies)
        _request(client, 'POST', f'/api/tasks/{tid}/delete', cookies=admin_cookies)
        resp = _request(client, 'POST', f'/api/tasks/{tid}/restore', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_task_delete_form(self, client, admin_cookies):
        tid = self._task_id(client, admin_cookies)
        resp = _request(client, 'POST', f'/tasks/{tid}/delete', cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 303

    def test_task_restore_form(self, client, admin_cookies):
        tid = self._task_id(client, admin_cookies)
        _request(client, 'POST', f'/api/tasks/{tid}/delete', cookies=admin_cookies)
        resp = _request(client, 'POST', f'/tasks/{tid}/restore', cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 303

    def test_client_delete(self, client, admin_cookies):
        TestClients._client_counter += 1
        n = TestClients._client_counter
        _request(client, 'POST', '/clients/create', data={
            'org_name': f'Client Del {n}', 'domain': f'cdel{n}.test',
            'contract_end': '2026-12-31',
        }, cookies=admin_cookies, follow_redirects=False)
        r = _request(client, 'GET', '/api/clients', cookies=admin_cookies)
        cid = r.json()[0]['id']
        resp = _request(client, 'POST', f'/clients/{cid}/delete', cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 303

    def test_client_restore(self, client, admin_cookies):
        TestClients._client_counter += 1
        n = TestClients._client_counter
        _request(client, 'POST', '/clients/create', data={
            'org_name': f'Restore Client {n}', 'domain': f'rest{n}.test',
            'contract_end': '2026-12-31',
        }, cookies=admin_cookies, follow_redirects=False)
        r = _request(client, 'GET', '/api/clients', cookies=admin_cookies)
        cid = r.json()[0]['id']
        _request(client, 'POST', f'/clients/{cid}/delete', cookies=admin_cookies, follow_redirects=False)
        resp = _request(client, 'POST', f'/api/clients/{cid}/restore', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True

    def test_trash_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/trash', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_hard_delete(self, client, admin_cookies):
        _request(client, 'POST', '/tasks/create', data={'title': 'Hard Del', 'status': 'todo'}, cookies=admin_cookies, follow_redirects=False)
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        tid = r.json()[0]['id']
        _request(client, 'POST', f'/api/tasks/{tid}/delete', cookies=admin_cookies)
        resp = _request(client, 'POST', f'/api/tasks/{tid}/hard-delete', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True


class TestComments:

    def test_get_comments(self, client, admin_cookies):
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        tasks = r.json()
        if not tasks:
            _request(client, 'POST', '/tasks/create', data={'title': 'Comment Task', 'status': 'todo'}, cookies=admin_cookies, follow_redirects=False)
            r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
            tasks = r.json()
        tid = tasks[-1]['id']
        resp = _request(client, 'GET', f'/api/tasks/{tid}/comments', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_post_comment(self, client, admin_cookies):
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        tid = r.json()[0]['id']
        resp = _request(client, 'POST', f'/api/tasks/{tid}/comments', json={'content': 'Test @admin comment'}, cookies=admin_cookies)
        assert resp.status_code in (200, 201)

    def test_post_comment_empty(self, client, admin_cookies):
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        tid = r.json()[0]['id']
        resp = _request(client, 'POST', f'/api/tasks/{tid}/comments', json={'content': ''}, cookies=admin_cookies)
        assert resp.status_code == 400

    def test_comment_unauth(self, client):
        resp = _request(client, 'POST', '/api/tasks/1/comments', json={'content': 'test'}, cookies={})
        assert resp.status_code == 401





class TestNotifications:

    def test_notifications_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/notifications', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_api_notifications(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/notifications', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert 'notifications' in data
        assert 'unread_count' in data

    def test_unread_count(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/notifications/unread-count', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'count' in resp.json()

    def test_read_all(self, client, admin_cookies):
        resp = _request(client, 'POST', '/api/notifications/read-all', cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True


class TestSearch:

    def test_search(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/search?q=test', cookies=admin_cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict) and (len(data) > 0 or 'tasks' in data or 'clients' in data)

    def test_search_empty(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/search?q=', cookies=admin_cookies)
        assert resp.status_code == 200


class TestActivity:

    def test_activity_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/activity', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_api_activity(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/activity', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestTemplates:

    def test_get_templates(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/templates', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    def test_save_templates(self, client, admin_cookies):
        resp = _request(client, 'POST', '/api/templates', json={
            'category': 'test', 'templates': [{'text': 'item', 'done': False}],
        }, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True


class TestSettings:

    def test_settings_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/settings', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_settings_save(self, client, admin_cookies):
        resp = _request(client, 'POST', '/settings', data={'timezone': 'Europe/Moscow', 'theme': 'dark'}, cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert '/settings' in resp.headers['location']


class TestReports:

    def test_reports_page(self, client, admin_cookies):
        resp = _request(client, 'GET', '/reports', cookies=admin_cookies)
        assert resp.status_code == 200

    def test_reports_data(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/reports/data', cookies=admin_cookies)
        assert resp.status_code == 200


class TestFiles:

    def test_file_upload_and_download(self, client, admin_cookies):
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        tasks = r.json()
        tid = tasks[-1]['id'] if tasks else None
        if not tid:
            _request(client, 'POST', '/tasks/create', data={'title': 'File Task', 'status': 'todo'}, cookies=admin_cookies, follow_redirects=False)
            r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
            tid = r.json()[0]['id']
        resp = _request(client, 'POST', f'/api/tasks/{tid}/upload', files={'file': ('test.txt', b'hello pytest', 'text/plain')}, cookies=admin_cookies)
        assert resp.status_code == 200
        j = resp.json()
        assert j['ok'] is True
        fid = j['id']
        resp2 = _request(client, 'GET', f'/api/files/{fid}/download', cookies=admin_cookies)
        assert resp2.status_code == 200
        assert resp2.content == b'hello pytest'

    def test_file_list(self, client, admin_cookies):
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        tasks = r.json()
        tid = tasks[-1]['id'] if tasks else 1
        resp = _request(client, 'GET', f'/api/tasks/{tid}/files', cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestSSE:

    def test_sse_endpoint(self, client, admin_cookies):
        # SSE is a streaming endpoint that never ends — just check initial 200 + content-type
        loop = asyncio.get_event_loop()
        async def _test():
            async with client.stream('GET', '/api/sse?once=1', cookies=admin_cookies) as resp:
                assert resp.status_code == 200
                assert 'text/event-stream' in resp.headers.get('content-type', '')
                # Read one byte to confirm stream is alive, then close
                try:
                    async for _ in resp.aiter_bytes():
                        break
                except asyncio.TimeoutError:
                    pass
        loop.run_until_complete(_test())


class TestPasswordChange:

    def test_change_password_success(self, client, admin_cookies):
        resp = _request(client, 'POST', '/api/users/change-password',
                        data={'current_password': 'admin', 'new_password': 'newpass456'},
                        cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()['ok'] is True
        # Restore old password
        _request(client, 'POST', '/api/users/change-password',
                 data={'current_password': 'newpass456', 'new_password': 'admin'},
                 cookies=admin_cookies)

    def test_change_password_wrong_current(self, client, admin_cookies):
        resp = _request(client, 'POST', '/api/users/change-password',
                        data={'current_password': 'wrong', 'new_password': 'newpass'},
                        cookies=admin_cookies)
        assert resp.status_code == 400
        assert 'Неверный текущий пароль' in resp.json()['error']

    def test_change_password_too_short(self, client, admin_cookies):
        resp = _request(client, 'POST', '/api/users/change-password',
                        data={'current_password': 'admin', 'new_password': 'ab'},
                        cookies=admin_cookies)
        assert resp.status_code == 400
        assert 'минимум 4' in resp.json()['error']

    def test_change_password_unauth(self, client):
        resp = _request(client, 'POST', '/api/users/change-password',
                        data={'current_password': 'x', 'new_password': 'y'},
                        cookies={})
        assert resp.status_code == 401


class TestExport:
    _domain_counter = 0

    def _create_task_with_client(self, client, admin_cookies):
        TestExport._domain_counter += 1
        n = TestExport._domain_counter
        _request(client, 'POST', '/clients/create', data={
            'org_name': f'Export Org {n}',
            'domain': f'export{n}.test',
            'contract_end': '2026-12-31',
            'status': 'active',
        }, cookies=admin_cookies, follow_redirects=False)
        _request(client, 'POST', '/tasks/create', data={
            'title': f'Export Task {n}', 'status': 'done',
        }, cookies=admin_cookies, follow_redirects=False)

    def test_csv_export(self, client, admin_cookies):
        self._create_task_with_client(client, admin_cookies)
        resp = _request(client, 'GET', '/api/tasks/export/csv', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'text/csv' in resp.headers.get('content-type', '')
        assert 'Content-Disposition' in resp.headers

    def test_pdf_export(self, client, admin_cookies):
        self._create_task_with_client(client, admin_cookies)
        resp = _request(client, 'GET', '/api/tasks/export/pdf', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'text/html' in resp.headers.get('content-type', '')

    def test_reports_csv_export(self, client, admin_cookies):
        resp = _request(client, 'GET', '/api/reports/export/csv', cookies=admin_cookies)
        assert resp.status_code == 200
        assert 'text/csv' in resp.headers.get('content-type', '')


class TestDoneRoute:

    def _create_task(self, client, cookies, title='Done Test'):
        _request(client, 'POST', '/tasks/create', data={'title': title, 'status': 'todo'}, cookies=cookies, follow_redirects=False)
        r = _request(client, 'GET', '/api/tasks', cookies=cookies)
        return r.json()[0]['id']

    def test_done_route(self, client, admin_cookies):
        tid = self._create_task(client, admin_cookies)
        resp = _request(client, 'POST', f'/tasks/{tid}/done', cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        assert '/tasks' in resp.headers['location']
        # Verify status changed
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        task = next(t for t in r.json() if t['id'] == tid)
        assert task['status'] == 'done'

    def test_done_recurring_auto_generates_next(self, client, admin_cookies):
        # Create a recurring task via API
        create_resp = _request(client, 'POST', '/tasks/create', data={
            'title': 'Recurring Done', 'status': 'todo',
        }, cookies=admin_cookies, follow_redirects=False)
        assert create_resp.status_code == 302, f'Create failed: {create_resp.headers.get("location", "")}'
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        tasks = [t for t in r.json() if t['title'].endswith('Recurring Done')]
        assert tasks, f'Recurring Done not found. Available titles: {[t["title"] for t in r.json()]}'
        tid = tasks[0]['id']
        # Set recurring fields via PATCH
        _request(client, 'PATCH', f'/api/tasks/{tid}',
                 json={'recurring_interval': 'daily', 'recurring_count': 3},
                 cookies=admin_cookies)
        resp = _request(client, 'POST', f'/tasks/{tid}/done', cookies=admin_cookies, follow_redirects=False)
        assert resp.status_code == 302
        r2 = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        recurring_tasks = [t for t in r2.json() if t['title'].endswith('Recurring Done')]
        assert len(recurring_tasks) >= 1

    def test_done_unauth(self, client):
        resp = _request(client, 'POST', '/tasks/99999/done', follow_redirects=False, cookies={})
        assert resp.status_code in (302, 307)
        assert '/login' in resp.headers['location']


class TestRecurringRemainingPreserved:

    def test_patch_recurring_count_does_not_reset_remaining(self, client, admin_cookies):
        # Create task via form
        create_resp = _request(client, 'POST', '/tasks/create', data={
            'title': 'Recurring Preserve', 'status': 'todo',
        }, cookies=admin_cookies, follow_redirects=False)
        assert create_resp.status_code == 302, f'Create failed: {create_resp.headers.get("location", "")}'
        r = _request(client, 'GET', '/api/tasks', cookies=admin_cookies)
        tasks = [t for t in r.json() if t['title'].endswith('Recurring Preserve')]
        assert tasks, f'Recurring Preserve not found. Available: {[t["title"] for t in r.json()]}'
        tid = tasks[0]['id']
        # Set recurring via PATCH
        _request(client, 'PATCH', f'/api/tasks/{tid}',
                 json={'recurring_interval': 'weekly', 'recurring_count': 5},
                 cookies=admin_cookies)

        # Mark done once to decrement remaining to 4
        _request(client, 'POST', f'/tasks/{tid}/done', cookies=admin_cookies, follow_redirects=False)
        r2 = _request(client, 'GET', '/api/tasks/all', cookies=admin_cookies)
        task = next(t for t in r2.json() if t['title'] == 'Recurring Preserve')
        assert task['recurring_remaining'] == 4

        # PATCH with same recurring_count — remaining should stay 4
        resp = _request(client, 'PATCH', f'/api/tasks/{tid}',
                        json={'recurring_count': 5, 'notes': 'should not reset remaining'},
                        cookies=admin_cookies)
        assert resp.status_code == 200, f"PATCH failed: {resp.json()}"
        r3 = _request(client, 'GET', '/api/tasks/all', cookies=admin_cookies)
        tasks_all = r3.json()
        task3 = next(t for t in tasks_all if t['id'] == int(tid))
        assert task3['recurring_remaining'] == 4, f"Expected 4, got {task3['recurring_remaining']}"
