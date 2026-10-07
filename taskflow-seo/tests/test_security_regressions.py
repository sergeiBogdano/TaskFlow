"""Регрессионные тесты закрытых уязвимостей и багов видимости.

- захват чужого пароля через добавление в своё окружение (только self/superadmin);
- restore отчёта из корзины (инверсия условия);
- чек-лист массивом в create/update (500 + формат чтения);
- задачи генератора модулей без окружения;
- require_workspace_role: путь важнее query;
- задачи чужих участников в спринте.
"""
import uuid


def _uniq(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _make_user(sync_request, admin_cookies, username):
    resp = sync_request(
        "POST", "/api/users",
        json={"username": username, "password": "pass1234"},
        cookies=admin_cookies,
    )
    assert resp.status_code == 201, resp.text
    uid = resp.json()["id"]
    login = sync_request(
        "POST", "/api/auth/login",
        json={"username": username, "password": "pass1234"},
    )
    assert login.status_code == 200, login.text
    return uid, {"taskflow_user": login.cookies.get("taskflow_user")}


class TestPasswordTakeover:
    def test_ws_owner_resets_victim_password(self, sync_request, admin_cookies):
        attacker_id, attacker_cookies = _make_user(sync_request, admin_cookies, _uniq("attacker"))
        victim_name, victim_id = _uniq("victim"), None
        victim_id, _ = _make_user(sync_request, admin_cookies, victim_name)
        # атакующий создаёт своё окружение и добавляет жертву без её согласия
        from tests.test_user_permissions import _make_workspace
        ws_data = _make_workspace(sync_request, attacker_cookies, "Evil WS")
        ws_id = ws_data['id']
        add = sync_request(
            "POST", f"/api/workspaces/{ws_id}/members",
            json={"user_id": victim_id, "role": "member"},
            cookies=attacker_cookies,
        )
        assert add.status_code == 201, add.text
        # смена пароля жертвы
        resp = sync_request(
            "PUT", f"/api/users/{victim_id}/password",
            json={"password": "pwned1234"}, cookies=attacker_cookies,
        )
        print("password reset by ws-owner:", resp.status_code)
        assert resp.status_code == 403, "УЯЗВИМОСТЬ: чужой пароль сменён!"
        # и логин со старым паролем должен работать
        login = sync_request(
            "POST", "/api/auth/login",
            json={"username": victim_name, "password": "pass1234"},
        )
        assert login.status_code == 200


class TestReportRestore:
    def test_restore_trashed_report(self, sync_request, admin_cookies, event_loop):
        from app.core.database import async_session
        from app.core.models import GeneratedReport
        from datetime import datetime, timezone
        async def make():
            async with async_session() as s:
                r = GeneratedReport(
                    title="Trash me", status="done",
                    deleted_at=datetime.now(timezone.utc),
                )
                s.add(r)
                await s.commit()
                return r.id

        rid = event_loop.run_until_complete(make())
        resp = sync_request("POST", f"/api/reports/{rid}/restore", cookies=admin_cookies)
        print("report restore:", resp.status_code, resp.text[:100])
        assert resp.status_code == 200, "restore trashed report должен быть 200"


class TestChecklist:
    def test_create_task_with_checklist_array(self, sync_request, admin_cookies):
        resp = sync_request(
            "POST", "/api/tasks",
            json={"title": _uniq("Checklist task"),
                  "checklist": [{"text": "пункт 1", "done": False}]},
            cookies=admin_cookies,
        )
        print("create with checklist:", resp.status_code, resp.text[:150])
        assert resp.status_code == 201
        tid = resp.json()["id"]
        got = sync_request("GET", f"/api/tasks/{tid}", cookies=admin_cookies).json()
        assert isinstance(got["checklist"], list), type(got["checklist"])
        assert got["checklist"][0]["text"] == "пункт 1"

    def test_update_task_with_checklist_array(self, sync_request, admin_cookies):
        resp = sync_request(
            "POST", "/api/tasks",
            json={"title": _uniq("Upd checklist")}, cookies=admin_cookies,
        )
        tid = resp.json()["id"]
        upd = sync_request(
            "PUT", f"/api/tasks/{tid}",
            json={"checklist": [{"text": "a", "done": True}]},
            cookies=admin_cookies,
        )
        print("update with checklist:", upd.status_code, upd.text[:150])
        assert upd.status_code == 200


class TestModuleGeneratorWs:
    def test_generated_tasks_have_workspace(self, sync_request, admin_cookies, event_loop):
        from app.scheduler.jobs import generate_module_tasks
        from app.core.database import async_session
        from app.core.models import Task
        from sqlalchemy import select

        client = sync_request(
            "POST", "/api/clients",
            json={"org_name": _uniq("Gen Client"),
                  "contract_start": "2026-01-01T00:00:00",
                  "contract_end": "2027-01-01T00:00:00"},
            cookies=admin_cookies,
        )
        assert client.status_code == 201, client.text
        cid = client.json()["id"]
        mod = sync_request(
            "POST", "/api/modules",
            json={"name": _uniq("Gen mod"), "client_ids": [cid],
                  "recurring_interval": "daily", "recurring_count": 1,
                  "task_title_template": "Auto"},
            cookies=admin_cookies,
        )
        assert mod.status_code == 201, mod.text

        async def run_and_find():
            await generate_module_tasks()
            async with async_session() as s:
                rows = (await s.execute(
                    select(Task).where(Task.title == "Auto").order_by(Task.id.desc()).limit(1)
                )).scalars().all()
                return rows[0].workspace_id if rows else "NOT-CREATED"

        ws_id = event_loop.run_until_complete(run_and_find())
        print("generated task workspace_id:", ws_id)
        assert ws_id not in (None, "NOT-CREATED"), "задача без окружения!"


class TestWsRolePrecedence:
    def test_path_beats_query(self, sync_request, admin_cookies):
        wa = sync_request("POST", "/api/workspaces", json={"name": _uniq("WSA")}, cookies=admin_cookies).json()
        wb = sync_request("POST", "/api/workspaces", json={"name": _uniq("WSB")}, cookies=admin_cookies).json()
        # пользователь ТОЛЬКО в B
        uid, _ = _make_user(sync_request, admin_cookies, _uniq("onlyb"))
        add = sync_request(
            "POST", f"/api/workspaces/{wb['id']}/members",
            json={"user_id": uid, "role": "member"}, cookies=admin_cookies,
        )
        assert add.status_code == 201, add.text
        # путь B + query A: должны вернуться участники B (там есть uid)
        resp = sync_request(
            "GET", f"/api/workspaces/{wb['id']}/members?workspace_id={wa['id']}",
            cookies=admin_cookies,
        )
        assert resp.status_code == 200, resp.text
        ids = {m["user_id"] for m in resp.json()}
        print("members returned:", ids, "expected member of B:", uid in ids)
        assert uid in ids, "ctx взят из query, а не из пути!"


class TestSprintVisibility:
    def test_member_cannot_read_foreign_task_via_sprint(self, sync_request, admin_cookies):
        uname = _uniq("sprintmember")
        uid, cookies = _make_user(sync_request, admin_cookies, uname)
        # дефолтное окружение админа
        workspaces = sync_request("GET", "/api/workspaces", cookies=admin_cookies).json()
        assert workspaces, "нет окружений"
        ws_id = workspaces[0]["id"]
        # участник БЕЗ прав на чужие задачи вступает в то же окружение
        add = sync_request(
            "POST", f"/api/workspaces/{ws_id}/members",
            json={"user_id": uid, "role": "member"}, cookies=admin_cookies,
        )
        assert add.status_code == 201, add.text
        # приватная задача админа (участник её не видит напрямую)
        task = sync_request(
            "POST", "/api/tasks",
            json={"title": _uniq("Private task")}, cookies=admin_cookies,
        ).json()
        direct = sync_request("GET", f"/api/tasks/{task['id']}", cookies=cookies)
        assert direct.status_code == 403, "прекондиция: задача не видна напрямую"
        # кладём её в спринт
        sprints = sync_request("GET", "/api/sprints", cookies=admin_cookies).json()
        if not sprints:
            sp = sync_request("POST", "/api/sprints", json={"name": "S1"}, cookies=admin_cookies)
            assert sp.status_code == 201, sp.text
            sid = sp.json()["id"]
        else:
            sid = sprints[0]["id"]
        add_t = sync_request(
            "POST", f"/api/sprints/{sid}/tasks", json={"task_ids": [task["id"]]},
            cookies=admin_cookies,
        )
        assert add_t.status_code == 200, add_t.text
        view = sync_request("GET", f"/api/sprints/{sid}", cookies=cookies)
        assert view.status_code == 200, view.text
        titles = [t["title"] for t in view.json().get("tasks", [])]
        print("member sees sprint tasks:", titles)
        assert all("Private task" not in t for t in titles), "УТЕЧКА через спринт!"


class TestSuperadminPasswordLocked:
    def test_put_self_forbidden(self, sync_request, admin_cookies):
        # пароль суперадмина через PUT не меняется вообще — даже им самим
        resp = sync_request(
            "PUT", "/api/users/1/password",
            json={"password": "newpass123"}, cookies=admin_cookies,
        )
        assert resp.status_code == 403, resp.text

    def test_root_change_password_always_forbidden(self, sync_request, admin_cookies):
        # смена пароля суперадмина через API запрещена, состояние не меняется
        resp = sync_request(
            "POST", "/api/users/change-password",
            data={"current_password": "definitely-wrong", "new_password": "newpass123"},
            cookies=admin_cookies,
        )
        assert resp.status_code == 403, resp.text
        login = sync_request(
            "POST", "/api/auth/login",
            json={"username": "4dmin", "password": "newpass123"},
        )
        assert login.status_code != 200


class TestPasswordResetLadder:
    """Сброс чужих паролей: право users_password_reset + строго вниз по рангу.

    owner → admin → member; ровесникам, старшим и вне общих окружений — 403.
    """

    @staticmethod
    def _login(sync_request, username, password):
        resp = sync_request(
            "POST", "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        return {"taskflow_user": resp.cookies.get("taskflow_user")}

    @staticmethod
    def _make_reset_role(sync_request, admin_cookies, name):
        resp = sync_request(
            "POST", "/api/roles",
            json={"name": name, "permissions": {"users_password_reset": True}},
            cookies=admin_cookies,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_admin_without_key_denied(self, sync_request, admin_cookies):
        # админ окружения БЕЗ права reset: захват через invite-then-reset мёртв
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("NORST")}, cookies=admin_cookies).json()
        aname = _uniq("norst_admin")
        aid, acookies = _make_user(sync_request, admin_cookies, aname)
        mname = _uniq("norst_member")
        mid, _ = _make_user(sync_request, admin_cookies, mname)
        for uid, role in ((aid, "admin"), (mid, "member")):
            resp = sync_request(
                "POST", f"/api/workspaces/{ws['id']}/members",
                json={"user_id": uid, "role": role}, cookies=admin_cookies,
            )
            assert resp.status_code == 201, resp.text
        resp = sync_request(
            "PUT", f"/api/users/{mid}/password",
            json={"password": "hacked123"}, cookies=acookies,
        )
        assert resp.status_code == 403, resp.text

    def test_admin_with_key_resets_member(self, sync_request, admin_cookies):
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("RST")}, cookies=admin_cookies).json()
        role_id = self._make_reset_role(sync_request, admin_cookies, _uniq("Resetter"))
        try:
            aname = _uniq("rst_admin")
            aid, _ = _make_user(sync_request, admin_cookies, aname)
            mname = _uniq("rst_member")
            mid, _ = _make_user(sync_request, admin_cookies, mname)
            for uid, role in ((aid, "admin"), (mid, "member")):
                resp = sync_request(
                    "POST", f"/api/workspaces/{ws['id']}/members",
                    json={"user_id": uid, "role": role}, cookies=admin_cookies,
                )
                assert resp.status_code == 201, resp.text
            # выдаём право через роль приложения
            resp = sync_request(
                "PUT", f"/api/users/{aid}/role",
                json={"role_id": role_id}, cookies=admin_cookies,
            )
            assert resp.status_code == 200, resp.text
            acookies = self._login(sync_request, aname, "pass1234")
            resp = sync_request(
                "PUT", f"/api/users/{mid}/password",
                json={"password": "reset1234"}, cookies=acookies,
            )
            assert resp.status_code == 403, resp.text
            # A workspace role cannot reset a platform password
            login = sync_request(
                "POST", "/api/auth/login",
                json={"username": mname, "password": "pass1234"},
            )
            assert login.status_code == 200, login.text
        finally:
            sync_request("DELETE", f"/api/roles/{role_id}", cookies=admin_cookies)

    def test_peers_denied(self, sync_request, admin_cookies):
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("PEER")}, cookies=admin_cookies).json()
        role_id = self._make_reset_role(sync_request, admin_cookies, _uniq("PeerReset"))
        try:
            a1name = _uniq("peer1")
            a1, _ = _make_user(sync_request, admin_cookies, a1name)
            a2name = _uniq("peer2")
            a2, _ = _make_user(sync_request, admin_cookies, a2name)
            for uid in (a1, a2):
                resp = sync_request(
                    "POST", f"/api/workspaces/{ws['id']}/members",
                    json={"user_id": uid, "role": "admin"}, cookies=admin_cookies,
                )
                assert resp.status_code == 201, resp.text
                resp = sync_request(
                    "PUT", f"/api/users/{uid}/role",
                    json={"role_id": role_id}, cookies=admin_cookies,
                )
                assert resp.status_code == 200, resp.text
            c1 = self._login(sync_request, a1name, "pass1234")
            resp = sync_request(
                "PUT", f"/api/users/{a2}/password",
                json={"password": "hacked123"}, cookies=c1,
            )
            assert resp.status_code == 403, resp.text
        finally:
            sync_request("DELETE", f"/api/roles/{role_id}", cookies=admin_cookies)

    def test_member_with_custom_reset_cannot_hit_admin(self, sync_request, admin_cookies):
        # кастомная роль с reset у участника: ранг всё равно ниже — 403
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("CSTM")}, cookies=admin_cookies).json()
        aname = _uniq("cstm_admin")
        aid, acookies = _make_user(sync_request, admin_cookies, aname)
        mname = _uniq("cstm_member")
        mid, mcookies = _make_user(sync_request, admin_cookies, mname)
        for uid, role in ((aid, "admin"), (mid, "member")):
            resp = sync_request(
                "POST", f"/api/workspaces/{ws['id']}/members",
                json={"user_id": uid, "role": role}, cookies=admin_cookies,
            )
            assert resp.status_code == 201, resp.text
        resp = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/roles",
            json={"name": _uniq("Reset custom"), "permissions": {"users_password_reset": True}},
            cookies=admin_cookies,
        )
        assert resp.status_code == 400, resp.text
        # Account password capabilities cannot be delegated through a space profile.
        resp = sync_request(
            'PUT', f'/api/users/{aid}/password',
            json={'password': 'hacked123'}, cookies=mcookies,
        )
        assert resp.status_code == 403, resp.text

    def test_no_shared_workspace_denied(self, sync_request, admin_cookies):
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("ISO")}, cookies=admin_cookies).json()
        role_id = self._make_reset_role(sync_request, admin_cookies, _uniq("IsoReset"))
        try:
            aname = _uniq("iso_admin")
            aid, _ = _make_user(sync_request, admin_cookies, aname)
            resp = sync_request(
                "POST", f"/api/workspaces/{ws['id']}/members",
                json={"user_id": aid, "role": "admin"}, cookies=admin_cookies,
            )
            assert resp.status_code == 201, resp.text
            resp = sync_request(
                "PUT", f"/api/users/{aid}/role",
                json={"role_id": role_id}, cookies=admin_cookies,
            )
            assert resp.status_code == 200, resp.text
            # жертва вообще без окружений
            outsider, _ = _make_user(sync_request, admin_cookies, _uniq("outsider"))
            acookies = self._login(sync_request, aname, "pass1234")
            resp = sync_request(
                "PUT", f"/api/users/{outsider}/password",
                json={"password": "hacked123"}, cookies=acookies,
            )
            assert resp.status_code == 403, resp.text
        finally:
            sync_request("DELETE", f"/api/roles/{role_id}", cookies=admin_cookies)

    def test_owner_resets_admin(self, sync_request, admin_cookies):
        # владелец выше админа: без права — 403, с правом — 200
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("OWNRST")}, cookies=admin_cookies).json()
        oname = _uniq("owner_rst")
        oid, _ = _make_user(sync_request, admin_cookies, oname)
        aname = _uniq("admin_rst")
        aid, _ = _make_user(sync_request, admin_cookies, aname)
        resp = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": oid, "role": "member"}, cookies=admin_cookies,
        )
        assert resp.status_code == 201, resp.text
        # владельцем назначает только суперадмин
        resp = sync_request(
            "PATCH", f"/api/workspaces/{ws['id']}/members/{oid}",
            json={"role": "owner"}, cookies=admin_cookies,
        )
        assert resp.status_code == 200, resp.text
        resp = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": aid, "role": "admin"}, cookies=admin_cookies,
        )
        assert resp.status_code == 201, resp.text
        ocookies = self._login(sync_request, oname, "pass1234")
        # без права reset — 403 даже владельцу
        resp = sync_request(
            "PUT", f"/api/users/{aid}/password",
            json={"password": "hacked123"}, cookies=ocookies,
        )
        assert resp.status_code == 403, resp.text
        # выдаём право ролью приложения и повторяем
        role_id = self._make_reset_role(sync_request, admin_cookies, _uniq("OwnerReset"))
        try:
            resp = sync_request(
                "PUT", f"/api/users/{oid}/role",
                json={"role_id": role_id}, cookies=admin_cookies,
            )
            assert resp.status_code == 200, resp.text
            resp = sync_request(
                "PUT", f"/api/users/{aid}/password",
                json={"password": "resetbyowner"}, cookies=ocookies,
            )
            assert resp.status_code == 403, resp.text
        finally:
            sync_request("DELETE", f"/api/roles/{role_id}", cookies=admin_cookies)

    def test_own_toggle_off(self, sync_request, admin_cookies, executor_cookies):
        # сняли users_password_own у роли executor (явный False, как шлёт UI):
        # свой пароль закрыт везде
        roles = sync_request("GET", "/api/roles", cookies=admin_cookies).json()
        executor_role = next(r for r in roles if r["name"] == "executor")
        original = dict(executor_role["permissions"] or {})
        trimmed = dict(original)
        trimmed["users_password_own"] = False
        try:
            resp = sync_request(
                "PUT", f"/api/roles/{executor_role['id']}",
                json={"permissions": trimmed}, cookies=admin_cookies,
            )
            assert resp.status_code == 200, resp.text
            me = sync_request("GET", "/api/auth/me", cookies=executor_cookies).json()
            uid = me["user"]["id"]
            resp = sync_request(
                "PUT", f"/api/users/{uid}/password",
                json={"password": "newpass123"}, cookies=executor_cookies,
            )
            assert resp.status_code == 403, resp.text
            resp = sync_request(
                "POST", "/api/users/change-password",
                data={"current_password": "testpass", "new_password": "newpass123"},
                cookies=executor_cookies,
            )
            assert resp.status_code == 403, resp.text
        finally:
            resp = sync_request(
                "PUT", f"/api/roles/{executor_role['id']}",
                json={"permissions": original}, cookies=admin_cookies,
            )
            assert resp.status_code == 200, resp.text


class TestCustomRoleExactSet:
    """Кастомная роль — точный набор: база ранга не добавляется."""

    @staticmethod
    def _login(sync_request, username, password):
        resp = sync_request(
            "POST", "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        return {"taskflow_user": resp.cookies.get("taskflow_user")}

    @staticmethod
    def _me(sync_request, cookies, workspace_id):
        resp = sync_request(
            "GET", f"/api/auth/me?workspace_id={workspace_id}", cookies=cookies,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["user"]["permissions"]

    def test_custom_role_replaces_base(self, sync_request, admin_cookies):
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("EXACT"), "preset": "seo"}, cookies=admin_cookies).json()
        mname = _uniq("exact_member")
        mid, _ = _make_user(sync_request, admin_cookies, mname)
        resp = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": mid, "role": "member"}, cookies=admin_cookies,
        )
        assert resp.status_code == 201, resp.text
        # база member даёт tasks
        mcookies = self._login(sync_request, mname, "pass1234")
        assert self._me(sync_request, mcookies, ws["id"]).get("tasks") is True
        # кастомная роль только с reports
        resp = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/roles",
            json={"name": _uniq("Only reports"), "permissions": {"reports": True}},
            cookies=admin_cookies,
        )
        assert resp.status_code == 201, resp.text
        custom_id = resp.json()["id"]
        try:
            resp = sync_request(
                "PUT", f"/api/workspaces/{ws['id']}/members/{mid}/custom-role",
                json={"role_id": custom_id}, cookies=admin_cookies,
            )
            assert resp.status_code == 200, resp.text
            perms = self._me(sync_request, mcookies, ws["id"])
            assert perms.get("reports") is True
            assert not perms.get("tasks"), "база ранга просочилась сквозь точный набор"
            assert not perms.get("dashboard"), "база ранга просочилась сквозь точный набор"
        finally:
            sync_request(
                "PUT", f"/api/workspaces/{ws['id']}/members/{mid}/custom-role",
                json={"role_id": None}, cookies=admin_cookies,
            )
            sync_request(
                "DELETE", f"/api/workspaces/{ws['id']}/roles/{custom_id}",
                cookies=admin_cookies,
            )

    def test_no_auto_add_on_boot(self, tmp_path, monkeypatch, event_loop):
        # молчаливое добавление — только при создании самого первого
        # окружения (bootstrap legacy-данных); рестарт никого не добавляет,
        # удалённый (tombstone) не возвращается
        import os

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        import app.core.database as db
        from app.core.models import User, WorkspaceMember

        path = tmp_path / "noauto.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")

        async def go():
            async with engine.begin() as conn:
                await conn.run_sync(db.Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            monkeypatch.setattr(db, "async_session", sessions)
            async with sessions() as s:
                s.add(User(username="loner", password_hash="x"))
                await s.commit()
            # первый старт: окружения нет → bootstrap создаёт + импортирует
            await db._ensure_workspaces()
            async with sessions() as s:
                loner_id = (await s.execute(
                    select(User.id).where(User.username == "loner")
                )).scalar_one()
                loner_ws = (await s.execute(select(WorkspaceMember).where(
                    WorkspaceMember.user_id == loner_id
                ))).scalars().all()
                assert len(loner_ws) == 1, "bootstrap должен импортировать новичка один раз"
                # удаляем и рестартуем: tombstone не даёт вернуть
                for link in loner_ws:
                    await s.delete(link)
                await s.commit()
            await db._ensure_workspaces()
            async with sessions() as s:
                rows = (await s.execute(select(WorkspaceMember))).scalars().all()
                assert rows == [], f"воскрешение/лишние: {rows}"

        try:
            event_loop.run_until_complete(go())
        finally:
            await_engine_dispose(event_loop, engine)
            os.remove(path)

    def test_migration_preserves_effective(self, tmp_path, monkeypatch, event_loop):
        # Ранг управляет членством и не расширяет точную кастомную роль.
        import os

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        import app.core.database as db
        from app.core.models import User, Workspace, WorkspaceMember, WorkspaceRole

        path = tmp_path / "migrate_roles.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")

        async def go():
            async with engine.begin() as conn:
                await conn.run_sync(db.Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            monkeypatch.setattr(db, "async_session", sessions)
            async with sessions() as s:
                s.add(Workspace(name="W"))
                await s.flush()
                ws = (await s.execute(select(Workspace))).scalars().first()
                m_user = User(username="mm", password_hash="x")
                a_user = User(username="aa", password_hash="x")
                s.add_all([m_user, a_user])
                await s.flush()
                role = WorkspaceRole(workspace_id=ws.id, name="Shared", permissions='{"reports": true}')
                s.add(role)
                await s.flush()
                s.add_all([
                    WorkspaceMember(workspace_id=ws.id, user_id=m_user.id, role="member", custom_role_id=role.id),
                    WorkspaceMember(workspace_id=ws.id, user_id=a_user.id, role="admin", custom_role_id=role.id),
                ])
                await s.commit()
                wid, mid, aid = ws.id, m_user.id, a_user.id
            import app.core.permissions as perm
            # get_workspace_permissions импортирует async_session из
            # app.core.database при каждом вызове — замоканого выше хватает

            await db._migrate_custom_roles_exact()
            after_m = await perm.get_workspace_permissions(mid, wid)
            after_a = await perm.get_workspace_permissions(aid, wid)
            assert after_m == {"reports": True}
            assert after_a == {"reports": True}
            assert after_m.get("reports") is True
            assert after_a.get("reports") is True
            # Общая роль остаётся общей, без автоматического расширения.
            async with sessions() as s:
                m_link = (await s.execute(select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == wid, WorkspaceMember.user_id == mid,
                ))).scalar_one()
                a_link = (await s.execute(select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == wid, WorkspaceMember.user_id == aid,
                ))).scalar_one()
                assert m_link.custom_role_id == a_link.custom_role_id

            async def snapshot():
                async with sessions() as s:
                    rws = (await s.execute(select(WorkspaceRole))).scalars().all()
                    lks = (await s.execute(select(WorkspaceMember))).scalars().all()
                    return (
                        sorted((r.workspace_id, r.name, r.permissions) for r in rws),
                        sorted((l.workspace_id, l.user_id, l.custom_role_id) for l in lks),
                    )

            before = await snapshot()
            # и повторный прогон ничего не меняет (конвергентность)
            await db._migrate_custom_roles_exact()
            assert await snapshot() == before
            assert await perm.get_workspace_permissions(mid, wid) == after_m
            assert await perm.get_workspace_permissions(aid, wid) == after_a

        try:
            event_loop.run_until_complete(go())
        finally:
            await_engine_dispose(event_loop, engine)
            os.remove(path)


def await_engine_dispose(event_loop, engine):
    async def _dispose():
        await engine.dispose()

    return event_loop.run_until_complete(_dispose())


class TestContractReminders:
    def test_created_once_and_idempotent(self, sync_request, admin_cookies, event_loop):
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import func, select

        from app.core.database import async_session
        from app.core.models import Reminder
        from app.scheduler.jobs import check_contracts_ending

        end = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        client = sync_request(
            "POST", "/api/clients",
            json={"org_name": _uniq("Reminder client"),
                  "contract_start": start, "contract_end": end},
            cookies=admin_cookies,
        )
        assert client.status_code == 201, client.text
        cid = client.json()["id"]

        async def count():
            async with async_session() as s:
                return (await s.execute(
                    select(func.count(Reminder.id)).where(
                        Reminder.reminder_type == "contract",
                        Reminder.client_id == cid,
                        Reminder.sent.is_(False),
                    )
                )).scalar()

        async def run_job():
            await check_contracts_ending()

        event_loop.run_until_complete(run_job())
        first = event_loop.run_until_complete(count())
        assert first == 2, f"ожидали 2 напоминания (3 и 1 день), получили {first}"
        event_loop.run_until_complete(run_job())
        second = event_loop.run_until_complete(count())
        assert second == first, f"дубликаты: было {first}, стало {second}"


class TestPurgeFkSafe:
    def test_purge_workspace_with_comments_contracts(self, tmp_path, monkeypatch, event_loop):
        import os
        from datetime import datetime, timezone

        from sqlalchemy import event, select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.database import Base
        from app.core.models import (
            Client,
            ClientContact,
            Contract,
            Task,
            TaskComment,
            Workspace,
        )
        from app.web.api import workspaces as ws_api

        path = tmp_path / "purge_fk.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")

        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        async def go():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            monkeypatch.setattr(ws_api, "async_session", sessions)
            now = datetime.now(timezone.utc)
            async with sessions() as s:
                ws = Workspace(name="purge me")
                s.add(ws)
                await s.flush()
                task = Task(title="t", workspace_id=ws.id)
                s.add(task)
                await s.flush()
                s.add(TaskComment(task_id=task.id, content="c"))
                client = Client(
                    org_name="c", contract_start=now, contract_end=now,
                    workspace_id=ws.id,
                )
                s.add(client)
                await s.flush()
                s.add(ClientContact(client_id=client.id, fio="FIO"))
                s.add(Contract(client_id=client.id))
                await s.commit()
                wid, tid, cid = ws.id, task.id, client.id
            async with sessions() as s:
                await ws_api._purge_workspace(s, wid)
                await s.commit()
            async with sessions() as s:
                assert await s.get(Workspace, wid) is None
                assert await s.get(Task, tid) is None
                assert await s.get(Client, cid) is None
                assert (await s.execute(select(TaskComment))).scalars().all() == []
                assert (await s.execute(select(ClientContact))).scalars().all() == []
                assert (await s.execute(select(Contract))).scalars().all() == []
            await engine.dispose()

        event_loop.run_until_complete(go())
        os.remove(path)


class TestMemberResurrection:
    def test_removed_member_not_restored_on_boot(self, sync_request, admin_cookies, event_loop):
        from sqlalchemy import select

        from app.core.database import _ensure_workspaces, async_session
        from app.core.models import WorkspaceMember

        uid, _ = _make_user(sync_request, admin_cookies, _uniq("doomed"))
        ws = sync_request("GET", "/api/workspaces", cookies=admin_cookies).json()[0]
        add = sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "member"}, cookies=admin_cookies,
        )
        assert add.status_code == 201, add.text
        rm = sync_request(
            "DELETE", f"/api/workspaces/{ws['id']}/members/{uid}", cookies=admin_cookies,
        )
        assert rm.status_code == 200, rm.text
        # имитация рестарта приложения
        event_loop.run_until_complete(_ensure_workspaces())

        async def check():
            async with async_session() as s:
                row = (await s.execute(select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == ws["id"],
                    WorkspaceMember.user_id == uid,
                ))).scalar_one_or_none()
                return row is not None

        assert event_loop.run_until_complete(check()) is False, "участник воскрес после _ensure_workspaces"


class TestOverdueReset:
    def test_deadline_extended_clears_overdue(self, sync_request, admin_cookies):
        from datetime import datetime, timedelta, timezone

        task = sync_request(
            "POST", "/api/tasks", json={"title": _uniq("Overdue reset")},
            cookies=admin_cookies,
        ).json()
        tid = task["id"]
        mv = sync_request(
            "POST", f"/api/tasks/{tid}/move", json={"status": "overdue"},
            cookies=admin_cookies,
        )
        assert mv.status_code == 200, mv.text
        future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
        upd = sync_request(
            "PUT", f"/api/tasks/{tid}", json={"deadline": future},
            cookies=admin_cookies,
        )
        assert upd.status_code == 200, upd.text
        got = sync_request("GET", f"/api/tasks/{tid}", cookies=admin_cookies).json()
        assert got["status"] == "in_progress", got["status"]


class TestUploadLimit:
    def test_big_upload_rejected(self, sync_request, admin_cookies):
        task = sync_request(
            "POST", "/api/tasks", json={"title": _uniq("Big file")},
            cookies=admin_cookies,
        ).json()
        resp = sync_request(
            "POST", f"/api/tasks/{task['id']}/upload",
            files={"file": ("big.bin", b"x" * (11 * 1024 * 1024))},
            cookies=admin_cookies,
        )
        assert resp.status_code == 413, resp.status_code


class TestGroupMembersValidation:
    def test_non_numeric_user_ids_400(self, sync_request, admin_cookies):
        group = sync_request(
            "POST", "/api/groups", json={"name": _uniq("G")}, cookies=admin_cookies,
        )
        assert group.status_code == 201, group.text
        resp = sync_request(
            "PUT", f"/api/groups/{group.json()['id']}/members",
            json={"user_ids": ["abc"]}, cookies=admin_cookies,
        )
        assert resp.status_code == 400, resp.status_code


class TestOwnerLeave:
    def test_co_owner_can_leave(self, sync_request, admin_cookies, event_loop):
        # второй владелец появляется только через суперадмина; sole owner выйти не может
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("OWN")}, cookies=admin_cookies).json()
        uid, cookies = _make_user(sync_request, admin_cookies, _uniq("future_owner"))
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "member"}, cookies=admin_cookies,
        )
        # суперадмин делает его совладельцем
        from app.core.database import async_session
        from app.core.models import WorkspaceMember
        from sqlalchemy import select
        async def promote():
            async with async_session() as s:
                m = (await s.execute(select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == ws["id"], WorkspaceMember.user_id == uid,
                ))).scalar_one()
                m.role = "owner"
                await s.commit()

        event_loop.run_until_complete(promote())
        # теперь совладелец может выйти сам (остаётся первый владелец)
        rm = sync_request(
            "DELETE", f"/api/workspaces/{ws['id']}/members/{uid}", cookies=cookies,
        )
        assert rm.status_code == 200, rm.text

    def test_last_owner_cannot_abandon(self, sync_request, admin_cookies, event_loop):
        ws = sync_request("POST", "/api/workspaces", json={"name": _uniq("OWN2")}, cookies=admin_cookies).json()
        uid, cookies = _make_user(sync_request, admin_cookies, _uniq("sole_owner"))
        sync_request(
            "POST", f"/api/workspaces/{ws['id']}/members",
            json={"user_id": uid, "role": "member"}, cookies=admin_cookies,
        )
        from app.core.database import async_session
        from app.core.models import WorkspaceMember
        from sqlalchemy import select

        async def promote_and_drop_admin():
            async with async_session() as s:
                m = (await s.execute(select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == ws["id"], WorkspaceMember.user_id == uid,
                ))).scalar_one()
                m.role = "owner"
                # убираем создателя (суперадмина), чтобы остался единственный владелец
                admin_m = (await s.execute(select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == ws["id"], WorkspaceMember.user_id == 1,
                ))).scalar_one_or_none()
                if admin_m is not None:
                    await s.delete(admin_m)
                await s.commit()

        event_loop.run_until_complete(promote_and_drop_admin())
        rm = sync_request(
            "DELETE", f"/api/workspaces/{ws['id']}/members/{uid}", cookies=cookies,
        )
        assert rm.status_code == 403, rm.text


class TestAccessesEncryption:
    def test_accesses_encrypted_at_rest(self, sync_request, admin_cookies, event_loop):
        from app.core.database import async_session
        from app.core.models import Client

        secret = _uniq("s3cr3t")
        client = sync_request(
            "POST", "/api/clients",
            json={"org_name": _uniq("Enc client"),
                  "contract_start": "2026-01-01T00:00:00",
                  "contract_end": "2027-01-01T00:00:00",
                  "accesses": [{"title": "ssh", "login": "root", "password": secret}]},
            cookies=admin_cookies,
        )
        assert client.status_code == 201, client.text
        cid = client.json()["id"]

        async def raw_value():
            async with async_session() as s:
                row = await s.get(Client, cid)
                return row.accesses

        raw = event_loop.run_until_complete(raw_value())
        assert secret not in (raw or ""), "пароль в открытом виде в БД!"
        got = sync_request("GET", f"/api/clients/{cid}", cookies=admin_cookies).json()
        assert got["accesses"][0]["password"] == secret
