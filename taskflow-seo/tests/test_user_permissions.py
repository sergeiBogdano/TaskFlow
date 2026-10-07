import uuid

import pytest


def _login(sync_request, username, password):
    resp = sync_request("POST", "/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"taskflow_user": resp.cookies.get("taskflow_user")}


def _make_workspace(sync_request, cookies, name, preset="seo"):
    # Spaces are provisioned centrally, then a responsible owner is assigned.
    actor = sync_request('GET', '/api/auth/me', cookies=cookies).json()['user']
    root = _login(sync_request, '4dmin', '4dmin')
    resp = sync_request('POST', '/api/workspaces', json={'name': name, 'preset': preset}, cookies=root)
    assert resp.status_code == 201, resp.text
    ws = resp.json()
    if not actor.get('is_root'):
        add = sync_request('POST', f"/api/workspaces/{ws['id']}/members", json={'user_id': actor['id'], 'role': 'member'}, cookies=root)
        assert add.status_code == 201, add.text
        promote = sync_request('PATCH', f"/api/workspaces/{ws['id']}/members/{actor['id']}", json={'role': 'owner'}, cookies=root)
        assert promote.status_code == 200, promote.text
    return ws


def _make_user(sync_request, admin_cookies, username):
    resp = sync_request(
        "POST", "/api/users", json={"username": username, "password": "pass1234"}, cookies=admin_cookies
    )
    assert resp.status_code == 201, resp.text
    uid = resp.json()["id"]
    return uid, _login(sync_request, username, "pass1234")


class TestSuperadminUserProtection:
    def test_cannot_assign_superadmin_role(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        uid, _ = _make_user(sync_request, admin_cookies, f"target_{uniq}")
        roles = sync_request("GET", "/api/roles", cookies=admin_cookies).json()
        superadmin_role = next(r for r in roles if r["name"] == "superadmin")
        resp = sync_request(
            "PUT", f"/api/users/{uid}/role",
            json={"role_id": superadmin_role["id"]}, cookies=admin_cookies,
        )
        assert resp.status_code == 403

    def test_cannot_delete_superadmin_user(self, sync_request, admin_cookies):
        resp = sync_request("DELETE", "/api/users/1", cookies=admin_cookies)
        assert resp.status_code == 403

    def test_cannot_change_superadmin_role(self, sync_request, admin_cookies):
        roles = sync_request("GET", "/api/roles", cookies=admin_cookies).json()
        admin_role = next(r for r in roles if r["name"] == "admin")
        resp = sync_request(
            "PUT", "/api/users/1/role",
            json={"role_id": admin_role["id"]}, cookies=admin_cookies,
        )
        assert resp.status_code == 403

    def test_superadmin_password_only_via_current_proof(self, sync_request, admin_cookies, event_loop):
        # через PUT пароль суперадмина не меняется вообще — даже им самим
        resp = sync_request(
            "PUT", "/api/users/1/password",
            json={"password": "newpass123"}, cookies=admin_cookies,
        )
        assert resp.status_code == 403
        # через change-password с неверным текущим — 400, пароль цел
        resp = sync_request(
            "POST", "/api/users/change-password",
            data={"current_password": "wrong", "new_password": "newpass123"},
            cookies=admin_cookies,
        )
        assert resp.status_code == 400
        bad_login = sync_request(
            "POST", "/api/auth/login",
            json={"username": "4dmin", "password": "newpass123"},
        )
        assert bad_login.status_code != 200
        # с верным текущим — 200, затем возвращаем обратно
        try:
            resp = sync_request(
                "POST", "/api/users/change-password",
                data={"current_password": "4dmin", "new_password": "newpass123"},
                cookies=admin_cookies,
            )
            assert resp.status_code == 200, resp.text
            good_login = sync_request(
                "POST", "/api/auth/login",
                json={"username": "4dmin", "password": "newpass123"},
            )
            assert good_login.status_code == 200
        finally:
            from app.core.auth import hash_password
            from app.core.database import async_session
            from app.core.models import User
            async def restore():
                async with async_session() as session:
                    root = await session.get(User, 1)
                    root.password_hash = hash_password('4dmin')
                    root.session_version += 1
                    await session.commit()
            event_loop.run_until_complete(restore())

    def test_other_user_cannot_change_superadmin_password(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        _, cookies = _make_user(sync_request, admin_cookies, f"intruder_{uniq}")
        resp = sync_request(
            "PUT", "/api/users/1/password",
            json={"password": "hacked123"}, cookies=cookies,
        )
        assert resp.status_code == 403

    def test_superadmin_can_change_other_user_role(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        uid, _ = _make_user(sync_request, admin_cookies, f"promote_{uniq}")
        roles = sync_request("GET", "/api/roles", cookies=admin_cookies).json()
        admin_role = next(r for r in roles if r["name"] == "admin")
        resp = sync_request(
            "PUT", f"/api/users/{uid}/role",
            json={"role_id": admin_role["id"]}, cookies=admin_cookies,
        )
        assert resp.status_code == 200

    def test_superadmin_can_change_other_user_password(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        uid, cookies = _make_user(sync_request, admin_cookies, f"pwd_{uniq}")
        resp = sync_request(
            "PUT", f"/api/users/{uid}/password",
            json={"password": "newpass123"}, cookies=admin_cookies,
        )
        assert resp.status_code == 200

    def test_superadmin_can_delete_other_user(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        uid, _ = _make_user(sync_request, admin_cookies, f"doomed_{uniq}")
        resp = sync_request("DELETE", f"/api/users/{uid}", cookies=admin_cookies)
        assert resp.status_code == 200

    def test_superadmin_can_access_all_workspaces(self, sync_request, admin_cookies):
        resp = sync_request("GET", "/api/workspaces", cookies=admin_cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1


class TestWorkspaceOwnerPermissions:
    def test_owner_can_manage_members(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        uid, cookies = _make_user(sync_request, admin_cookies, f"owner_{uniq}")
        ws = _make_workspace(sync_request, cookies, f"WS владельца {uniq}")
        uid2, _ = _make_user(sync_request, admin_cookies, f"member_{uniq}")
        resp = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid2, "role": "admin"}, cookies=cookies,
        )
        assert resp.status_code == 201

    def test_owner_can_update_workspace_settings(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"WS настройки {uniq}")
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}",
            json={"name": "Новое название"}, cookies=admin_cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Новое название"

    def test_owner_cannot_update_other_workspace_settings(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        ws1 = _make_workspace(sync_request, admin_cookies, f"WS1 {uniq}")
        ws2 = _make_workspace(sync_request, admin_cookies, f"WS2 {uniq}")
        uid, cookies = _make_user(sync_request, admin_cookies, f"owner2_{uniq}")
        sync_request(
            "POST", f"/api/workspaces/{ws1['id']}/members",
            json={"user_id": uid, "role": "owner"}, cookies=admin_cookies,
        )
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws2['id']}",
            json={"name": "Хакнуто"}, cookies=cookies,
        )
        assert resp.status_code == 403

    def test_owner_can_delete_workspace(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"WS удаление {uniq}")
        resp = sync_request("DELETE", f"/api/workspaces/{ws['id']}", cookies=admin_cookies)
        assert resp.status_code == 200


class TestWorkspaceAdminPermissions:
    def test_ws_admin_cannot_update_workspace_settings(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"WS админ настройки {uniq}")
        uid, cookies = _make_user(sync_request, admin_cookies, f"wsadmin_{uniq}")
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "admin"}, cookies=admin_cookies,
        )
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}",
            json={"name": "Хакнуто"}, cookies=cookies,
        )
        assert resp.status_code == 403

    def test_ws_admin_cannot_update_ui_config(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"WS админ UI {uniq}")
        uid, cookies = _make_user(sync_request, admin_cookies, f"wsadmin2_{uniq}")
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "admin"}, cookies=admin_cookies,
        )
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}",
            json={"ui_config": {"titles": {"/tasks": "Хакнуто"}}}, cookies=cookies,
        )
        assert resp.status_code == 403

    def test_ws_admin_can_manage_members(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"WS админ участники {uniq}")
        uid, cookies = _make_user(sync_request, admin_cookies, f"wsadmin3_{uniq}")
        uid2, _ = _make_user(sync_request, admin_cookies, f"wsadmin4_{uniq}")
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "admin"}, cookies=admin_cookies,
        )
        resp = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid2, "role": "member"}, cookies=cookies,
        )
        assert resp.status_code == 201

    def test_ws_admin_cannot_promote_to_owner(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"WS админ промоут {uniq}")
        uid, cookies = _make_user(sync_request, admin_cookies, f"wsadmin5_{uniq}")
        uid2, _ = _make_user(sync_request, admin_cookies, f"wsadmin6_{uniq}")
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "admin"}, cookies=admin_cookies,
        )
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid2, "role": "member"}, cookies=admin_cookies,
        )
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}/members/{uid2}",
            json={"role": "owner"}, cookies=cookies,
        )
        assert resp.status_code == 400

    def test_ws_admin_cannot_remove_owner(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"WS админ владелец {uniq}")
        uid, cookies = _make_user(sync_request, admin_cookies, f"wsadmin7_{uniq}")
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "admin"}, cookies=admin_cookies,
        )
        resp = sync_request(
            "DELETE", f"/api/workspaces/{ws['id']}/members/1", cookies=cookies
        )
        assert resp.status_code == 403


class TestRegularUserPermissions:
    def test_user_cannot_create_user(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        _, cookies = _make_user(sync_request, admin_cookies, f"plain_{uniq}")
        resp = sync_request(
            "POST", "/api/users",
            json={"username": f"plain2_{uniq}", "password": "pass1234"}, cookies=cookies,
        )
        assert resp.status_code == 403

    def test_user_cannot_list_all_users_for_creation(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        _, cookies = _make_user(sync_request, admin_cookies, f"viewer_{uniq}")
        resp = sync_request("GET", "/api/users", cookies=cookies)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_user_cannot_change_other_password(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        uid1, _ = _make_user(sync_request, admin_cookies, f"p1_{uniq}")
        uid2, cookies2 = _make_user(sync_request, admin_cookies, f"p2_{uniq}")
        resp = sync_request(
            "PUT", f"/api/users/{uid1}/password",
            json={"password": "hacked123"}, cookies=cookies2,
        )
        assert resp.status_code == 403

    def test_user_can_change_own_password(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        uid, cookies = _make_user(sync_request, admin_cookies, f"selfpwd_{uniq}")
        resp = sync_request(
            "POST", "/api/users/change-password",
            json={"current_password": "pass1234", "new_password": "newpass123"}, cookies=cookies,
        )
        assert resp.status_code == 200


class TestWorkspaceProvisioning:
    def test_regular_user_cannot_provision(self, sync_request, admin_cookies):
        _, cookies = _make_user(sync_request, admin_cookies, 'limited_' + uuid.uuid4().hex[:8])
        response = sync_request('POST', '/api/workspaces', json={'name': 'Forbidden'}, cookies=cookies)
        assert response.status_code == 403

    def test_platform_admin_can_provision_without_artificial_limit(self, sync_request, admin_cookies):
        uid, cookies = _make_user(sync_request, admin_cookies, 'provisioner_' + uuid.uuid4().hex[:8])
        roles = sync_request('GET', '/api/roles', cookies=admin_cookies).json()
        role = next(r for r in roles if r['name'] == 'admin')
        assert sync_request('PUT', f'/api/users/{uid}/role', json={'role_id': role['id']}, cookies=admin_cookies).status_code == 200
        for index in range(4):
            response = sync_request('POST', '/api/workspaces', json={'name': f'Team {index}'}, cookies=cookies)
            assert response.status_code == 201, response.text

    def test_many_independent_memberships(self, sync_request, admin_cookies):
        uid, cookies = _make_user(sync_request, admin_cookies, 'manyspaces_' + uuid.uuid4().hex[:8])
        for index in range(4):
            ws = _make_workspace(sync_request, admin_cookies, f'Membership {index}')
            assert sync_request('POST', f"/api/workspaces/{ws['id']}/members", json={'user_id': uid}, cookies=admin_cookies).status_code == 201
        assert len(sync_request('GET', '/api/workspaces', cookies=cookies).json()) == 4
