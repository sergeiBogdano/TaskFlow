"""Security regression scenarios for profiles, personal exceptions and field policies."""
import uuid


def setup_member(request, root, *, level='member'):
    suffix = uuid.uuid4().hex[:8]
    ws = request('POST', '/api/workspaces', json={'name': 'access_' + suffix, 'preset': 'seo'}, cookies=root).json()
    account = request('POST', '/api/users', json={'username': 'access_' + suffix, 'password': 'pass1234'}, cookies=root).json()
    response = request('POST', f"/api/workspaces/{ws['id']}/members", json={'user_id': account['id'], 'role': level}, cookies=root)
    assert response.status_code == 201, response.text
    login = request('POST', '/api/auth/login', json={'username': account['username'], 'password': 'pass1234'})
    return ws['id'], account['id'], {'taskflow_user': login.cookies['taskflow_user']}


def test_fields_are_enforced_on_server_and_personal_override_is_scoped(sync_request, admin_cookies):
    ws, uid, cookies = setup_member(sync_request, admin_cookies)
    profile = sync_request('POST', f'/api/workspaces/{ws}/roles', cookies=admin_cookies, json={
        'name': 'Limited fields', 'permissions': {'tasks': True, 'tasks_edit': True, 'calendar': True},
        'field_access': {'tasks': {'notes': 'hidden', 'deadline': 'view', 'sprint': 'hidden'}},
    })
    assert profile.status_code == 201, profile.text
    assert sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/custom-role',
                        json={'role_id': profile.json()['id']}, cookies=admin_cookies).status_code == 200
    task = sync_request('POST', f'/api/tasks?workspace_id={ws}', cookies=admin_cookies,
                        json={'title': 'Visible title', 'notes': 'PRIVATE_FIELD_MARKER', 'deadline': '2026-12-12', 'assignee_id': uid}).json()
    response = sync_request('GET', f"/api/tasks/{task['id']}", cookies=cookies)
    assert response.status_code == 200, response.text
    assert 'notes' not in response.json() and 'sprint_ids' not in response.json()
    assert response.json()['deadline'] == task['deadline']
    for values in ({'notes': 'changed'}, {'deadline': '2026-12-13'}):
        assert sync_request('PUT', f"/api/tasks/{task['id']}", cookies=cookies, json=values).status_code == 403
    assert sync_request('PUT', f"/api/tasks/{task['id']}", cookies=cookies, json={'priority': 'high'}).status_code == 200
    assert sync_request('POST', f'/api/tasks/bulk?workspace_id={ws}', cookies=cookies,
                        json={'ids': [task['id']], 'fields': {'deadline': '2026-12-13'}}).status_code == 403
    assert sync_request('PATCH', f"/api/calendar/{task['id']}", cookies=cookies,
                        json={'deadline': '2026-12-13'}).status_code == 403
    found = sync_request('GET', f'/api/tasks?workspace_id={ws}&search=PRIVATE_FIELD_MARKER', cookies=cookies)
    assert found.status_code == 200 and found.json() == []
    assert sync_request('GET', f"/api/tasks/{task['id']}/activity", cookies=cookies).status_code == 403
    override = sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/access', cookies=admin_cookies,
                            json={'fields': {'tasks': {'notes': 'edit'}}})
    assert override.status_code == 200, override.text
    assert sync_request('GET', f"/api/tasks/{task['id']}", cookies=cookies).json()['notes'] == 'PRIVATE_FIELD_MARKER'
    other = sync_request('POST', '/api/workspaces', cookies=admin_cookies, json={'name': 'Another_' + uuid.uuid4().hex[:8], 'preset': 'seo'}).json()
    assert sync_request('GET', f"/api/tasks?workspace_id={other['id']}", cookies=cookies).status_code == 403


def test_personal_deny_and_profile_action_permissions(sync_request, admin_cookies):
    ws, uid, cookies = setup_member(sync_request, admin_cookies)
    role = sync_request('POST', f'/api/workspaces/{ws}/roles', cookies=admin_cookies,
                        json={'name': 'View only', 'permissions': {'tasks': True, 'kanban': True}}).json()
    sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/custom-role', cookies=admin_cookies, json={'role_id': role['id']})
    assert sync_request('POST', f'/api/tasks?workspace_id={ws}', cookies=cookies, json={'title': 'No write'}).status_code == 403
    assert sync_request('POST', f'/api/sprints?workspace_id={ws}', cookies=cookies, json={'name': 'No planning'}).status_code == 403
    assert sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/access', cookies=admin_cookies,
                        json={'permissions': {'tasks': False}}).status_code == 200
    assert sync_request('GET', f'/api/tasks?workspace_id={ws}', cookies=cookies).status_code == 403
    report = sync_request('GET', f'/api/workspaces/{ws}/access', cookies=admin_cookies).json()
    member = next(item for item in report['members'] if item['user_id'] == uid)
    assert member['permissions']['tasks']['allowed'] is False
    assert member['permissions']['tasks']['source'] == 'Личное исключение'
    assert sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/access', cookies=admin_cookies, json={}).status_code == 200
    assert sync_request('GET', f'/api/tasks?workspace_id={ws}', cookies=cookies).status_code == 200


def test_management_permissions_do_not_bypass_hierarchy_or_own_access(sync_request, admin_cookies):
    ws, uid, cookies = setup_member(sync_request, admin_cookies, level='admin')
    owner = next(item for item in sync_request('GET', f'/api/workspaces/{ws}/members', cookies=admin_cookies).json() if item['role'] == 'owner')
    for target in (uid, owner['user_id']):
        assert sync_request('PUT', f'/api/workspaces/{ws}/members/{target}/access', cookies=cookies, json={}).status_code == 403
    profile = sync_request('POST', f'/api/workspaces/{ws}/roles', cookies=admin_cookies,
                           json={'name': 'No administration', 'permissions': {'workspace': True}}).json()
    assert sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/custom-role', cookies=admin_cookies,
                        json={'role_id': profile['id']}).status_code == 200
    assert sync_request('PATCH', f'/api/workspaces/{ws}', cookies=cookies, json={'name': 'Denied'}).status_code == 403
    assert sync_request('GET', f'/api/workspaces/{ws}/access', cookies=cookies).status_code == 403
    assert sync_request('POST', f'/api/workspaces/{ws}/roles', cookies=cookies,
                        json={'name': 'Escalation', 'permissions': {'workspace_profiles': True}}).status_code == 403


def test_field_policy_validation(sync_request, admin_cookies):
    ws, _, _ = setup_member(sync_request, admin_cookies)
    for fields in ({'tasks': {'title': 'hidden'}}, {'tasks': {'deadline': {}}}, {'unknown': {}}, {'tasks': {'unknown': 'edit'}}):
        response = sync_request('POST', f'/api/workspaces/{ws}/roles', cookies=admin_cookies,
                                json={'name': uuid.uuid4().hex, 'permissions': {}, 'field_access': fields})
        assert response.status_code == 400, response.text


def test_combined_access_save_and_feature_inheritance(sync_request, admin_cookies):
    ws, uid, _ = setup_member(sync_request, admin_cookies)
    enabled = sync_request('PUT', f'/api/workspaces/{ws}/modules', cookies=admin_cookies, json={'enabled': ['tasks', 'crm', 'notes', 'reports', 'automation', 'ai']})
    assert enabled.status_code == 200, enabled.text
    restored = sync_request('PUT', '/api/features', cookies=admin_cookies, json={'scope': 'workspace', 'target_id': ws, 'key': 'ai', 'enabled': True})
    assert restored.status_code == 200, restored.text
    path = f'/api/workspaces/{ws}/members/{uid}/access'
    response = sync_request('PUT', path, cookies=admin_cookies, json={'permissions': {'ai': True}, 'fields': {'tasks': {'notes': 'view'}}, 'function_availability': {'ai': False}})
    assert response.status_code == 200, response.text
    def actual():
        report = sync_request('GET', f'/api/workspaces/{ws}/access', cookies=admin_cookies).json()
        return next(row for row in report['members'] if row['user_id'] == uid)
    row = actual()
    assert row['permissions']['ai']['granted'] is True
    assert row['permissions']['ai']['available'] is False
    assert row['permissions']['ai']['availability_override'] is False
    assert row['fields']['tasks']['notes'] == 'view'
    response = sync_request('PUT', path, cookies=admin_cookies, json={'permissions': {'ai': True}, 'fields': {}, 'function_availability': {'ai': None}})
    assert response.status_code == 200, response.text
    row = actual()
    assert row['permissions']['ai']['allowed'] is True
    assert row['permissions']['ai']['availability_override'] is None


def test_combined_access_invalid_patch_does_not_partially_save(sync_request, admin_cookies):
    ws, uid, _ = setup_member(sync_request, admin_cookies)
    path = f'/api/workspaces/{ws}/members/{uid}/access'
    before = sync_request('GET', f'/api/workspaces/{ws}/access', cookies=admin_cookies).json()
    for function_changes in ({'ai': 'true'}, {'users_manage': True}, []):
        response = sync_request('PUT', path, cookies=admin_cookies, json={'permissions': {'tasks': False}, 'fields': {}, 'function_availability': function_changes})
        assert response.status_code == 400, response.text
        after = sync_request('GET', f'/api/workspaces/{ws}/access', cookies=admin_cookies).json()
        assert before == after


def test_combined_access_function_changes_require_actual_root(sync_request, admin_cookies):
    ws, uid, cookies = setup_member(sync_request, admin_cookies, level='admin')
    response = sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/access', cookies=cookies, json={'permissions': {'tasks': False}, 'function_availability': {'ai': True}})
    assert response.status_code == 403
    report = sync_request('GET', f'/api/workspaces/{ws}/access', cookies=admin_cookies).json()
    row = next(row for row in report['members'] if row['user_id'] == uid)
    assert row['permissions']['tasks']['allowed'] is True
    assert row['permissions']['ai']['availability_override'] is None


def test_combined_access_cannot_reopen_disabled_space_function(sync_request, admin_cookies):
    ws, uid, _ = setup_member(sync_request, admin_cookies)
    enabled = sync_request('PUT', f'/api/workspaces/{ws}/modules', cookies=admin_cookies, json={'enabled': ['tasks', 'crm', 'notes', 'reports', 'automation', 'ai']})
    assert enabled.status_code == 200, enabled.text
    restored = sync_request('PUT', '/api/features', cookies=admin_cookies, json={'scope': 'workspace', 'target_id': ws, 'key': 'ai', 'enabled': True})
    assert restored.status_code == 200, restored.text
    granted = sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/access', cookies=admin_cookies, json={'permissions': {'ai': True}, 'fields': {}, 'function_availability': {'ai': True}})
    assert granted.status_code == 200, granted.text
    disabled = sync_request('PUT', '/api/features', cookies=admin_cookies, json={'scope': 'workspace', 'target_id': ws, 'key': 'ai', 'enabled': False})
    assert disabled.status_code == 200
    response = sync_request('PUT', f'/api/workspaces/{ws}/members/{uid}/access', cookies=admin_cookies, json={'permissions': {'ai': True}, 'fields': {}, 'function_availability': {'ai': True}})
    assert response.status_code == 403, response.text
    report = sync_request('GET', f'/api/workspaces/{ws}/access', cookies=admin_cookies).json()
    row = next(row for row in report['members'] if row['user_id'] == uid)
    assert row['permissions']['ai']['granted'] is True
    assert row['permissions']['ai']['availability_override'] is True
    assert row['permissions']['ai']['allowed'] is False
    assert 'пространства' in row['permissions']['ai']['reason']
