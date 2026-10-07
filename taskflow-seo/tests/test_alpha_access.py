"""Alpha regressions: shared profiles, deterministic gates and honest settings."""
import uuid
import pytest
from tests.test_ws_roles import TestWsRoles as _WsHelpers


def account(sync_request, root, space_id, rank='member'):
    uid, cookies = _WsHelpers._make_user(sync_request, root, 'alpha_' + uuid.uuid4().hex[:10])
    response = sync_request('POST', f'/api/workspaces/{space_id}/members', json={'user_id': uid, 'role': rank}, cookies=root)
    assert response.status_code == 201, response.text
    return uid, cookies


def profile(sync_request, root, space_id, uid, permissions):
    response = _WsHelpers._create_role(sync_request, root, space_id, 'Profile ' + uuid.uuid4().hex[:8], permissions)
    assert response.status_code == 201, response.text
    role_id = response.json()['id']
    response = sync_request('PUT', f'/api/workspaces/{space_id}/members/{uid}/custom-role', json={'role_id': role_id}, cookies=root)
    assert response.status_code == 200, response.text
    return role_id


def test_assigned_role_cannot_disappear_and_expand_access(sync_request, admin_cookies):
    ws = _WsHelpers._make_ws(sync_request, admin_cookies)['id']
    uid, cookies = account(sync_request, admin_cookies, ws)
    role = profile(sync_request, admin_cookies, ws, uid, {'tasks': True})
    response = sync_request('DELETE', f'/api/workspaces/{ws}/roles/{role}', cookies=admin_cookies)
    assert response.status_code == 409
    me = sync_request('GET', f'/api/auth/me?workspace_id={ws}', cookies=cookies).json()['user']
    assert me['permissions'].get('tasks')
    assert not me['permissions'].get('clients')


def test_shared_role_update_obeys_rank_and_own_ceiling(sync_request, admin_cookies):
    ws = _WsHelpers._make_ws(sync_request, admin_cookies)['id']
    actor, cookies = account(sync_request, admin_cookies, ws, 'admin')
    peer, _ = account(sync_request, admin_cookies, ws, 'admin')
    member, _ = account(sync_request, admin_cookies, ws)
    own = profile(sync_request, admin_cookies, ws, actor, {'tasks': True})
    peer_role = profile(sync_request, admin_cookies, ws, peer, {'tasks': True})
    member_role = profile(sync_request, admin_cookies, ws, member, {'tasks': True})
    for role in (own, peer_role):
        response = sync_request('PUT', f'/api/workspaces/{ws}/roles/{role}', json={'permissions': {'tasks': True}}, cookies=cookies)
        assert response.status_code == 403, response.text
    response = sync_request('PUT', f'/api/workspaces/{ws}/roles/{member_role}', json={'permissions': {'tasks': True}}, cookies=cookies)
    assert response.status_code == 200, response.text
    response = sync_request('PUT', f'/api/workspaces/{ws}/members/{member}/custom-role', json={'role_id': None}, cookies=cookies)
    assert response.status_code == 403, response.text


@pytest.mark.parametrize('denial_first', [True, False])
def test_conflicting_group_switches_deny_independently_of_order(sync_request, admin_cookies, denial_first):
    ws = _WsHelpers._make_ws(sync_request, admin_cookies)['id']
    uid, cookies = account(sync_request, admin_cookies, ws)
    for enabled in ([False, True] if denial_first else [True, False]):
        response = sync_request('POST', '/api/groups', json={'name': 'Alpha ' + uuid.uuid4().hex[:8], 'permissions': {}}, cookies=admin_cookies)
        assert response.status_code == 201
        group = response.json()['id']
        assert sync_request('PUT', f'/api/groups/{group}/members', json={'user_ids': [uid, uid]}, cookies=admin_cookies).status_code == 200
        assert sync_request('PUT', '/api/features', json={'scope': 'group', 'target_id': group, 'key': 'tasks', 'enabled': enabled}, cookies=admin_cookies).status_code == 200
    response = sync_request('GET', f'/api/tasks?workspace_id={ws}', cookies=cookies)
    assert response.status_code == 403, response.text
    # Higher-priority explicit space policy still takes precedence over groups.
    assert sync_request('PUT', '/api/features', json={'scope': 'workspace', 'target_id': ws, 'key': 'tasks', 'enabled': True}, cookies=admin_cookies).status_code == 200
    assert sync_request('GET', f'/api/tasks?workspace_id={ws}', cookies=cookies).status_code == 200


def test_feature_panel_reports_policy_instead_of_root_emergency_access(sync_request, admin_cookies):
    ws = _WsHelpers._make_ws(sync_request, admin_cookies)['id']
    sync_request('PUT', '/api/features', json={'scope': 'workspace', 'target_id': ws, 'key': 'tasks', 'enabled': False}, cookies=admin_cookies)
    response = sync_request('GET', f'/api/features?scope=workspace&target_id={ws}&workspace_id={ws}', cookies=admin_cookies)
    assert response.status_code == 200, response.text
    assert response.json()['effective']['tasks'] is True
    assert response.json()['scope_effective']['tasks'] is False
    assert sync_request('GET', '/api/features?scope=user&target_id=99999999', cookies=admin_cookies).status_code == 404


@pytest.mark.parametrize('permissions', [[], {'tasks': 'false'}, {'all': True}, {'unknown': True}])
@pytest.mark.parametrize('endpoint', ['/api/groups', '/api/roles'])
def test_role_group_payload_rejects_ambiguous_permissions(sync_request, admin_cookies, endpoint, permissions):
    response = sync_request('POST', endpoint, json={'name': 'Invalid ' + uuid.uuid4().hex[:8], 'permissions': permissions}, cookies=admin_cookies)
    assert response.status_code == 400, response.text


def test_disabled_account_workspace_creation_is_enforced(sync_request, admin_cookies):
    ws = _WsHelpers._make_ws(sync_request, admin_cookies)['id']
    uid, cookies = account(sync_request, admin_cookies, ws)
    roles = sync_request('GET', '/api/roles', cookies=admin_cookies).json()
    role = next(role for role in roles if role['name'] == 'admin')
    sync_request('PUT', f'/api/users/{uid}/role', json={'role_id': role['id']}, cookies=admin_cookies)
    cookies = _WsHelpers._login(sync_request, next(u['username'] for u in sync_request('GET', '/api/users?scope=platform', cookies=admin_cookies).json() if u['id'] == uid), 'pass1234')
    sync_request('PUT', '/api/features', json={'scope': 'user', 'target_id': uid, 'key': 'workspaces_create', 'enabled': False}, cookies=admin_cookies)
    response = sync_request('POST', '/api/workspaces', json={'name': 'Forbidden'}, cookies=cookies)
    assert response.status_code == 403, response.text


def test_account_manager_can_read_directory_but_cannot_edit_roles(sync_request, admin_cookies):
    uid, cookies = _WsHelpers._make_user(sync_request, admin_cookies, 'accounts_' + uuid.uuid4().hex[:8])
    role = sync_request('POST', '/api/roles', json={'name': 'Account manager ' + uuid.uuid4().hex[:8], 'permissions': {'users_manage': True}}, cookies=admin_cookies)
    assert role.status_code == 201, role.text
    assert sync_request('PUT', f'/api/users/{uid}/role', json={'role_id': role.json()['id']}, cookies=admin_cookies).status_code == 200
    assert sync_request('GET', '/api/users?scope=platform', cookies=cookies).status_code == 200
    assert sync_request('GET', '/api/roles', cookies=cookies).status_code == 200
    assert sync_request('PUT', f"/api/roles/{role.json()['id']}", json={'permissions': {'users': True}}, cookies=cookies).status_code == 403
    assert sync_request('PUT', '/api/features', json={'scope': 'user', 'target_id': uid, 'key': 'users_manage', 'enabled': False}, cookies=admin_cookies).status_code == 200
    assert [u['id'] for u in sync_request('GET', '/api/users?scope=platform', cookies=cookies).json()] == [uid]
    assert sync_request('GET', '/api/roles', cookies=cookies).status_code == 403


def test_password_feature_disable_does_not_deadlock_onboarding(sync_request, admin_cookies):
    username = 'password_' + uuid.uuid4().hex[:8]
    created = sync_request('POST', '/api/users', json={'username': username, 'password': 'original123', 'must_change_password': True}, cookies=admin_cookies)
    assert created.status_code == 201
    uid = created.json()['id']
    assert sync_request('PUT', '/api/features', json={'scope': 'user', 'target_id': uid, 'key': 'users_password_own', 'enabled': False}, cookies=admin_cookies).status_code == 200
    cookies = _WsHelpers._login(sync_request, username, 'original123')
    response = sync_request('POST', '/api/users/change-password', json={'current_password': 'original123', 'new_password': 'permanent123'}, cookies=cookies)
    assert response.status_code == 200, response.text
    cookies = _WsHelpers._login(sync_request, username, 'permanent123')
    response = sync_request('POST', '/api/users/change-password', json={'current_password': 'permanent123', 'new_password': 'another123'}, cookies=cookies)
    assert response.status_code == 403, response.text


@pytest.mark.parametrize('endpoint', ['/api/groups', '/api/roles', '/api/features'])
def test_security_settings_require_json_object(sync_request, admin_cookies, endpoint):
    method = 'PUT' if endpoint == '/api/features' else 'POST'
    response = sync_request(method, endpoint, json=[], cookies=admin_cookies)
    assert response.status_code == 400, response.text
