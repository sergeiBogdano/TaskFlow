"""Exercise independent accounts and teams through the HTTP API."""
import uuid

from tests.test_user_permissions import _make_user, _make_workspace


def test_uninvited_account_stays_isolated_after_restart(sync_request, admin_cookies, event_loop):
    from app.core.database import _ensure_workspaces

    uid, cookies = _make_user(sync_request, admin_cookies, 'isolated_' + uuid.uuid4().hex[:10])
    assert sync_request('GET', '/api/workspaces', cookies=cookies).json() == []
    event_loop.run_until_complete(_ensure_workspaces())
    assert sync_request('GET', '/api/workspaces', cookies=cookies).json() == []
    users = sync_request('GET', '/api/users', cookies=cookies).json()
    assert [u['id'] for u in users] == [uid]


def test_two_teams_and_shared_member_permissions(sync_request, admin_cookies):
    suffix = uuid.uuid4().hex[:10]
    aid, a = _make_user(sync_request, admin_cookies, 'team_a_' + suffix)
    bid, b = _make_user(sync_request, admin_cookies, 'team_b_' + suffix)
    mid, member = _make_user(sync_request, admin_cookies, 'shared_' + suffix)
    wa = _make_workspace(sync_request, a, 'A ' + suffix)
    wb = _make_workspace(sync_request, b, 'B ' + suffix)
    for ws, owner in ((wa, a), (wb, b)):
        response = sync_request('POST', f"/api/workspaces/{ws['id']}/members",
                                json={'user_id': mid, 'role': 'member'}, cookies=owner)
        assert response.status_code == 201, response.text
    for ws, outsider in ((wa, b), (wb, a)):
        assert sync_request('GET', f"/api/workspaces/{ws['id']}", cookies=outsider).status_code == 403
        assert sync_request('GET', f"/api/tasks/all?workspace_id={ws['id']}", cookies=outsider).status_code == 403
    role = sync_request('POST', f"/api/workspaces/{wa['id']}/roles",
                        json={'name': 'Reports', 'permissions': {'reports': True}}, cookies=a)
    assert role.status_code == 201, role.text
    assigned = sync_request('PUT', f"/api/workspaces/{wa['id']}/members/{mid}/custom-role",
                            json={'role_id': role.json()['id']}, cookies=a)
    assert assigned.status_code == 200, assigned.text
    for ws, expected in ((wa, True), (wb, False), (wa, True)):
        me = sync_request('GET', f"/api/auth/me?workspace_id={ws['id']}", cookies=member).json()['user']
        assert bool(me['permissions'].get('reports')) is expected
    foreign = sync_request('PUT', f"/api/workspaces/{wb['id']}/members/{mid}/custom-role",
                           json={'role_id': role.json()['id']}, cookies=b)
    assert foreign.status_code == 404


def test_admin_cannot_delegate_privileged_profile(sync_request, admin_cookies):
    suffix = uuid.uuid4().hex[:10]
    aid, actor = _make_user(sync_request, admin_cookies, 'delegate_' + suffix)
    mid, _ = _make_user(sync_request, admin_cookies, 'recipient_' + suffix)
    ws = _make_workspace(sync_request, admin_cookies, 'Delegation ' + suffix)
    for uid, rank in ((aid, 'admin'), (mid, 'member')):
        assert sync_request('POST', f"/api/workspaces/{ws['id']}/members",
                            json={'user_id': uid, 'role': rank}, cookies=admin_cookies).status_code == 201
    profile = sync_request('POST', f"/api/workspaces/{ws['id']}/roles",
                           json={'name': 'Reset', 'permissions': {'users_password_reset': True}},
                           cookies=admin_cookies)
    assert profile.status_code == 201, profile.text
    response = sync_request('PUT', f"/api/workspaces/{ws['id']}/members/{mid}/custom-role",
                            json={'role_id': profile.json()['id']}, cookies=actor)
    assert response.status_code == 403
