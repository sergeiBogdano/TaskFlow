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


class TestWorkspaces:

    def test_default_workspace_exists(self, sync_request, admin_cookies):
        resp = sync_request("GET", "/api/workspaces", cookies=admin_cookies)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        assert any(w["role"] == "owner" for w in resp.json())

    def test_create_study_preset(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Учёба ТС", preset="study")
        assert ws["role"] == "owner"
        assert ws["theme"] == "cream"
        assert ws["dictionary"].get("clients") == "Проекты"
        resp = sync_request("GET", f"/api/sprints?workspace_id={ws['id']}", cookies=admin_cookies)
        assert resp.status_code == 200
        assert any(s["name"] == "Неделя 1: старт" for s in resp.json())

    def test_create_requires_name(self, sync_request, admin_cookies):
        resp = sync_request("POST", "/api/workspaces", json={"name": "  "}, cookies=admin_cookies)
        assert resp.status_code == 400

    def test_update_settings_owner(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Настройки ТС")
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}",
            json={"theme": "graphite", "dictionary": {"clients": "Проекты"}},
            cookies=admin_cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["theme"] == "graphite"

    def test_update_settings_member_forbidden(self, sync_request, admin_cookies, executor_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Чужие настройки ТС")
        # executor — участник дефолтного воркспейса, но не этого
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}", json={"theme": "graphite"}, cookies=executor_cookies
        )
        assert resp.status_code == 403


class TestIsolation:

    def test_tasks_isolated_by_workspace(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Изоляция ТС")
        resp = sync_request(
            "POST", f"/api/tasks?workspace_id={ws['id']}",
            json={"title": "Задача в изоляции"}, cookies=admin_cookies,
        )
        assert resp.status_code == 201
        tid = resp.json()["id"] if isinstance(resp.json(), dict) and "id" in resp.json() else None

        resp = sync_request("GET", "/api/tasks/all?scope=all", cookies=admin_cookies)
        titles = [t["title"] for t in resp.json()]
        assert "Задача в изоляции" not in titles

        resp = sync_request("GET", f"/api/tasks/all?scope=all&workspace_id={ws['id']}", cookies=admin_cookies)
        assert resp.status_code == 200
        assert any(t["title"] == "Задача в изоляции" for t in resp.json())
        if tid is not None:
            resp = sync_request("GET", f"/api/tasks/{tid}?workspace_id={ws['id']}", cookies=admin_cookies)
            assert resp.status_code in (200, 404)

    def test_member_cannot_access_foreign_workspace(self, sync_request, admin_cookies, executor_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Чужой ТС")
        resp = sync_request("GET", f"/api/tasks/all?scope=all&workspace_id={ws['id']}", cookies=executor_cookies)
        assert resp.status_code == 403

    def test_notes_scoped(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Заметки ТС")
        resp = sync_request(
            "POST", f"/api/notes?workspace_id={ws['id']}",
            json={"title": "Локальная для ТС"}, cookies=admin_cookies,
        )
        assert resp.status_code == 201
        resp = sync_request("GET", "/api/notes", cookies=admin_cookies)
        assert all(n["title"] != "Локальная для ТС" for n in resp.json()["notes"])
        resp = sync_request("GET", f"/api/notes?workspace_id={ws['id']}", cookies=admin_cookies)
        assert any(n["title"] == "Локальная для ТС" for n in resp.json()["notes"])


class TestOwnerProtection:

    def _setup(self, sync_request, admin_cookies, suffix):
        uniq = uuid.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"Владелец ТС {suffix} {uniq}")
        uid, cookies = _make_user(sync_request, admin_cookies, f"wsmember_{suffix}_{uniq}")
        resp = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "admin"}, cookies=admin_cookies,
        )
        assert resp.status_code == 201
        return ws, uid, cookies

    def test_admin_cannot_touch_owner(self, sync_request, admin_cookies):
        ws, uid, cookies = self._setup(sync_request, admin_cookies, "a")
        admin_id = 1
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}/members/{admin_id}",
            json={"role": "member"}, cookies=cookies,
        )
        assert resp.status_code == 403
        resp = sync_request("DELETE", f"/api/workspaces/{ws['id']}/members/{admin_id}", cookies=cookies)
        assert resp.status_code == 403
        resp = sync_request("DELETE", f"/api/workspaces/{ws['id']}", cookies=cookies)
        assert resp.status_code == 403

    def test_owner_password_only_superadmin(self, sync_request, admin_cookies):
        ws, uid, cookies = self._setup(sync_request, admin_cookies, "b")
        admin_id = 1
        resp = sync_request(
            "PUT", f"/api/users/{admin_id}/password", json={"password": "hacked123"}, cookies=cookies
        )
        assert resp.status_code == 403

    def test_superadmin_can_delete_workspace(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Под снос ТС")
        resp = sync_request(
            "POST", f"/api/tasks?workspace_id={ws['id']}",
            json={"title": "Умрёт с воркспейсом"}, cookies=admin_cookies,
        )
        assert resp.status_code == 201
        resp = sync_request("DELETE", f"/api/workspaces/{ws['id']}", cookies=admin_cookies)
        assert resp.status_code == 200
        resp = sync_request("GET", f"/api/tasks/all?scope=all&workspace_id={ws['id']}", cookies=admin_cookies)
        assert resp.status_code == 404


class TestPasswords:

    def test_self_change(self, sync_request, admin_cookies, executor_cookies):
        me = sync_request("GET", "/api/auth/me", cookies=executor_cookies).json()
        uid = me["user"]["id"]
        resp = sync_request("PUT", f"/api/users/{uid}/password", json={"password": "newpass123"}, cookies=executor_cookies)
        assert resp.status_code == 403
        wrong = sync_request("POST", "/api/users/change-password",
            json={"current_password": "wrong", "new_password": "newpass123"}, cookies=executor_cookies)
        assert wrong.status_code == 400
        resp = sync_request("POST", "/api/users/change-password",
            json={"current_password": "testpass", "new_password": "newpass123"}, cookies=executor_cookies)
        assert resp.status_code == 200
        assert sync_request("GET", "/api/auth/me", cookies=executor_cookies).status_code == 401
        login = sync_request("POST", "/api/auth/login", json={"username": "testexec", "password": "newpass123"})
        assert login.status_code == 200
        restored = sync_request("POST", "/api/users/change-password",
            json={"current_password": "newpass123", "new_password": "testpass"},
            cookies={"taskflow_user": login.cookies.get("taskflow_user")})
        assert restored.status_code == 200

    def test_member_cannot_change_admin_password(self, sync_request, admin_cookies, executor_cookies):
        resp = sync_request("PUT", "/api/users/1/password", json={"password": "hacked123"}, cookies=executor_cookies)
        assert resp.status_code == 403


class TestSprints:

    def test_sprint_crud_and_progress(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Спринты ТС")
        resp = sync_request(
            "POST", f"/api/sprints?workspace_id={ws['id']}",
            json={"name": "Спринт 1", "goal": "Проверить прогресс"}, cookies=admin_cookies,
        )
        assert resp.status_code == 201
        sid = resp.json()["id"]

        tids = []
        for title in ("STask A", "STask B"):
            r = sync_request(
                "POST", f"/api/tasks?workspace_id={ws['id']}", json={"title": title}, cookies=admin_cookies
            )
            assert r.status_code == 201
            tids.append(r.json()["id"] if isinstance(r.json(), dict) and "id" in r.json() else None)
        tids = [t for t in tids if t]
        assert len(tids) == 2

        resp = sync_request("POST", f"/api/sprints/{sid}/tasks", json={"task_ids": tids}, cookies=admin_cookies)
        assert resp.status_code == 200

        resp = sync_request("PUT", f"/api/tasks/{tids[0]}", json={"status": "done", "unfinished_policy": "keep"}, cookies=admin_cookies)
        assert resp.status_code == 200

        resp = sync_request("GET", f"/api/sprints/{sid}", cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()["progress"] == {"total": 2, "done": 1, "percent": 50}

        resp = sync_request("PATCH", f"/api/sprints/{sid}", json={"status": "done", "unfinished_policy": "keep"}, cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"

    def test_sprint_rejects_foreign_tasks(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Чужие задачи ТС")
        resp = sync_request(
            "POST", f"/api/sprints?workspace_id={ws['id']}", json={"name": "Изоляция"}, cookies=admin_cookies
        )
        sid = resp.json()["id"]
        r = sync_request("POST", "/api/tasks", json={"title": "Задача дефолта"}, cookies=admin_cookies)
        assert r.status_code == 201
        default_tid = r.json()["id"]
        resp = sync_request("POST", f"/api/sprints/{sid}/tasks", json={"task_ids": [default_tid]}, cookies=admin_cookies)
        assert resp.status_code == 400

    def test_sprint_delete_keeps_tasks(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Удаление спринта ТС")
        sid = sync_request(
            "POST", f"/api/sprints?workspace_id={ws['id']}", json={"name": "Временный"}, cookies=admin_cookies
        ).json()["id"]
        tid = sync_request(
            "POST", f"/api/tasks?workspace_id={ws['id']}", json={"title": "Переживёт спринт"}, cookies=admin_cookies
        ).json()["id"]
        sync_request("POST", f"/api/sprints/{sid}/tasks", json={"task_ids": [tid]}, cookies=admin_cookies)
        assert sync_request("DELETE", f"/api/sprints/{sid}", cookies=admin_cookies).status_code == 200
        assert sync_request("GET", f"/api/tasks/{tid}", cookies=admin_cookies).status_code == 200


class TestKnowledge:
    def test_chat_remember(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Память ТС")
        resp = sync_request(
            "POST", "/api/ai/chat",
            json={"message": "Запомни: клиент любит отчёты по пятницам", "workspace_id": ws["id"]},
            cookies=admin_cookies,
        )
        assert resp.status_code == 200
        assert resp.json()["intent"] == "draft_only"
        resp = sync_request("GET", f"/api/workspaces/{ws['id']}/knowledge", cookies=admin_cookies)
        assert not any("пятницам" in f["fact"] for f in resp.json())


class TestWorkspaceTrash:

    def test_soft_delete_hides_and_restores(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Корзина ТС")
        wid = ws["id"]
        resp = sync_request("DELETE", f"/api/workspaces/{wid}", cookies=admin_cookies)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "permanent": False}

        assert sync_request("GET", f"/api/workspaces/{wid}", cookies=admin_cookies).status_code == 404
        resp = sync_request("GET", "/api/workspaces", cookies=admin_cookies)
        assert all(w["id"] != wid for w in resp.json())

        resp = sync_request("GET", "/api/workspaces?deleted=true", cookies=admin_cookies)
        assert any(w["id"] == wid for w in resp.json())

        resp = sync_request("POST", f"/api/workspaces/{wid}/restore", cookies=admin_cookies)
        assert resp.status_code == 200
        assert sync_request("GET", f"/api/workspaces/{wid}", cookies=admin_cookies).status_code == 200

    def test_member_cannot_delete(self, sync_request, admin_cookies, executor_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Чужая корзина ТС")
        me = sync_request("GET", "/api/auth/me", cookies=executor_cookies).json()["user"]
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": me["id"], "role": "member"}, cookies=admin_cookies,
        )
        resp = sync_request("DELETE", f"/api/workspaces/{ws['id']}", cookies=executor_cookies)
        assert resp.status_code == 403
        resp = sync_request("POST", f"/api/workspaces/{ws['id']}/restore", cookies=executor_cookies)
        assert resp.status_code == 403

    def test_permanent_delete_cascades(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Снос навсегда ТС")
        wid = ws["id"]
        tid = sync_request(
            "POST", f"/api/tasks?workspace_id={wid}", json={"title": "Умрёт навсегда"}, cookies=admin_cookies
        ).json()["id"]
        resp = sync_request("DELETE", f"/api/workspaces/{wid}?permanent=true", cookies=admin_cookies)
        assert resp.json() == {"ok": True, "permanent": True}
        assert sync_request("GET", f"/api/tasks/{tid}", cookies=admin_cookies).status_code in (403, 404)

    def test_autopurge_old_deleted(self, sync_request, admin_cookies, event_loop):
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.core.database import async_session
        from app.core.models import Workspace

        ws = _make_workspace(sync_request, admin_cookies, "Протухшая ТС")
        wid = ws["id"]
        sync_request("DELETE", f"/api/workspaces/{wid}", cookies=admin_cookies)

        async def backdate():
            async with async_session() as session:
                row = await session.get(Workspace, wid)
                row.deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
                await session.commit()

        event_loop.run_until_complete(backdate())

        from app.scheduler.jobs import autopurge_trash
        event_loop.run_until_complete(autopurge_trash())

        async def exists():
            async with async_session() as session:
                return await session.get(Workspace, wid)

        assert event_loop.run_until_complete(exists()) is None
class TestUiConfig:

    def test_patch_and_read(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Интерфейс ТС")
        cfg = {"nav": {"/tasks": {"label": "Дела", "visible": False}}, "titles": {"/tasks": "Дела"}}
        resp = sync_request("PATCH", f"/api/workspaces/{ws['id']}", json={"ui_config": cfg}, cookies=admin_cookies)
        assert resp.status_code == 200
        resp = sync_request("GET", f"/api/workspaces/{ws['id']}", cookies=admin_cookies)
        assert resp.json()["ui_config"]["nav"]["/tasks"]["label"] == "Дела"

    def test_rejects_non_dict_and_oversize(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Интерфейс лимиты ТС")
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}", json={"ui_config": ["nope"]}, cookies=admin_cookies
        )
        assert resp.status_code in (400, 422)
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}", json={"ui_config": {"x": "y" * 60000}}, cookies=admin_cookies
        )
        assert resp.status_code == 400

    def test_member_cannot_patch(self, sync_request, admin_cookies, executor_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Интерфейс чужой ТС")
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}", json={"ui_config": {}}, cookies=executor_cookies
        )
        assert resp.status_code == 403

    def test_admin_with_settings_permission_can_patch_ui_config(self, sync_request, admin_cookies):
        import uuid as uuid_mod
        uniq = uuid_mod.uuid4().hex[:8]
        ws = _make_workspace(sync_request, admin_cookies, f"Интерфейс админ ТС {uniq}")
        uid = _make_user(sync_request, admin_cookies, f"wsadmin_{uniq}")[0]
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "admin"}, cookies=admin_cookies,
        )
        # логинимся админом окружения
        login = sync_request("POST", "/api/auth/login", json={"username": f"wsadmin_{uniq}", "password": "pass1234"})
        cookies = {"taskflow_user": login.cookies.get("taskflow_user")}
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}", json={"ui_config": {"titles": {"/tasks": "Дела"}}},
            cookies=cookies,
        )
        assert resp.status_code == 200
        # Администратор с явным разрешением может менять настройки
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}", json={"name": f"Переименовано {uniq}"}, cookies=cookies
        )
        assert resp.status_code == 200

    def test_labels_truncated(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Интерфейс обрезка ТС")
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}",
            json={"ui_config": {"nav": {"/tasks": {"label": "x" * 100}}, "titles": {"/tasks": "y" * 100}}},
            cookies=admin_cookies,
        )
        assert resp.status_code == 200
        data = sync_request("GET", f"/api/workspaces/{ws['id']}", cookies=admin_cookies).json()
        assert data["ui_config"]["nav"]["/tasks"]["label"] == "x" * 40
        assert data["ui_config"]["titles"]["/tasks"] == "y" * 60

    def test_project_preset(self, sync_request, admin_cookies):
        ws = _make_workspace(sync_request, admin_cookies, "Проект ТС", preset="project")
        assert ws["preset"] == "project"
        resp = sync_request("GET", f"/api/workspaces/{ws['id']}", cookies=admin_cookies).json()
        assert resp["dictionary"].get("clients") == "Проекты"
        sprints = sync_request("GET", f"/api/sprints?workspace_id={ws['id']}", cookies=admin_cookies).json()
        assert any(s["name"] == "Спринт 1: MVP" for s in sprints)
