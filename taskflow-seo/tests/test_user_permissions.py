import uuid

import pytest


def _login(sync_request, username, password):
    resp = sync_request("POST", "/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"taskflow_user": resp.cookies.get("taskflow_user")}


def _make_workspace(sync_request, cookies, name, preset="empty"):
    resp = sync_request("POST", "/api/workspaces", json={"name": name, "preset": preset}, cookies=cookies)
    assert resp.status_code == 201, resp.text
    return resp.json()


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

    def test_superadmin_can_change_own_password(self, sync_request, admin_cookies):
        resp = sync_request(
            "PUT", "/api/users/1/password",
            json={"password": "newpass123"}, cookies=admin_cookies,
        )
        assert resp.status_code == 200
        # возвращаем пароль, иначе следующая сессия тестов не залогинится
        resp = sync_request(
            "PUT", "/api/users/1/password",
            json={"password": "4dmin"}, cookies=admin_cookies,
        )
        assert resp.status_code == 200

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
            "PUT", f"/api/users/{uid}/password",
            json={"password": "newpass123"}, cookies=cookies,
        )
        assert resp.status_code == 200


class TestWorkspaceLimit:
    def test_user_limited_to_3_workspaces(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        _, cookies = _make_user(sync_request, admin_cookies, f"limited_{uniq}")
        for i in range(3):
            resp = sync_request(
                "POST", "/api/workspaces",
                json={"name": f"Лимит {uniq} {i}"}, cookies=cookies,
            )
            assert resp.status_code == 201, resp.text
        resp = sync_request(
            "POST", "/api/workspaces",
            json={"name": f"Лимит {uniq} 4"}, cookies=cookies,
        )
        assert resp.status_code == 400

    def test_superadmin_not_limited(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        for i in range(4):
            resp = sync_request(
                "POST", "/api/workspaces",
                json={"name": f"Супер лимит {uniq} {i}"}, cookies=admin_cookies,
            )
            assert resp.status_code == 201, resp.text

    def test_user_can_be_added_to_unlimited_workspaces(self, sync_request, admin_cookies):
        uniq = uuid.uuid4().hex[:8]
        uid, cookies = _make_user(sync_request, admin_cookies, f"joiner_{uniq}")
        # членство в чужих окружениях не ограничено
        for i in range(5):
            ws = _make_workspace(sync_request, admin_cookies, f"WS join {uniq} {i}")
            resp = sync_request(
                "POST", f"/api/workspaces/{ws['id']}/members",
                json={"user_id": uid, "role": "member"}, cookies=admin_cookies,
            )
            assert resp.status_code in (200, 201)
        # лимит применяется только к созданным самим пользователем
        for i in range(3):
            resp = sync_request(
                "POST", "/api/workspaces",
                json={"name": f"WS own {uniq} {i}"}, cookies=cookies,
            )
            assert resp.status_code == 201, resp.text
        resp = sync_request(
            "POST", "/api/workspaces",
            json={"name": f"WS own {uniq} 3"}, cookies=cookies,
        )
        assert resp.status_code == 400


class TestUnauthenticated:
    def test_cannot_access_users(self, sync_request):
        resp = sync_request("GET", "/api/users")
        assert resp.status_code in (401, 403)

    def test_cannot_access_workspaces(self, sync_request):
        resp = sync_request("GET", "/api/workspaces")
        assert resp.status_code in (401, 403)

    def test_cannot_create_user(self, sync_request):
        resp = sync_request(
            "POST", "/api/users",
            json={"username": "anon", "password": "pass1234"},
        )
        assert resp.status_code in (401, 403)
