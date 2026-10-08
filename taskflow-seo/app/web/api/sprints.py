"""Спринты: отрезок времени + набор задач + прогресс."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import Sprint, SprintTask, Task
from app.core.permissions import (
    get_accessible_client_ids,
    get_current_user,
    get_user_role_names, request_permissions,
    resolve_workspace,
    task_is_visible_to_user,
    task_is_editable_by_user,
    user_is_superadmin,
)

from app.core.access_policy import redact_fields, assert_field_writes

router = APIRouter(prefix="/api/sprints", tags=["sprints"])


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "Некорректная дата спринта")


async def _progress(session, sprint: Sprint) -> dict:
    rows = (await session.execute(
        select(Task.status).join(SprintTask, SprintTask.task_id == Task.id)
        .where(SprintTask.sprint_id == sprint.id, Task.deleted_at.is_(None))
    )).scalars().all()
    total = len(rows)
    done = sum(1 for status in rows if status == "done")
    return {"total": total, "done": done, "percent": round(done / total * 100) if total else 0}


def _sprint_to_dict(sprint: Sprint, progress: dict | None = None) -> dict:
    return redact_fields("sprints", {
        "id": sprint.id,
        "workspace_id": sprint.workspace_id,
        "name": sprint.name,
        "goal": sprint.goal or "",
        "start_date": sprint.start_date.date().isoformat() if sprint.start_date else None,
        "end_date": sprint.end_date.date().isoformat() if sprint.end_date else None,
        "status": sprint.status,
        "progress": progress or {"total": 0, "done": 0, "percent": 0},
        "created_at": sprint.created_at.isoformat() if sprint.created_at else None,
    })


class SprintCreate(BaseModel):
    name: str
    goal: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class SprintUpdate(BaseModel):
    unfinished_policy: str | None = None
    carryover_sprint_id: int | None = None
    name: str | None = None
    goal: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None


@router.get("")
async def list_sprints(workspace_id: int | None = None, user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, _ = await resolve_workspace(session, user, role_names, workspace_id)
        sprints = (await session.execute(
            select(Sprint).where(Sprint.workspace_id == workspace.id).order_by(Sprint.id.desc())
        )).scalars().all()
        out = []
        for sprint in sprints:
            out.append(_sprint_to_dict(sprint, await _progress(session, sprint)))
        return JSONResponse(out)


@router.post("", status_code=201)
async def create_sprint(payload: SprintCreate, workspace_id: int | None = None, user=Depends(get_current_user)):
    assert_field_writes("sprints", payload.model_dump(exclude_unset=True))
    name = (payload.name or "").strip()
    if not name:
        return JSONResponse({"error": "Нужно название"}, status_code=400)
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, _ = await resolve_workspace(session, user, role_names, workspace_id)
        sprint = Sprint(
            workspace_id=workspace.id,
            name=name[:200],
            goal=(payload.goal or "")[:2000] or None,
            start_date=_parse_dt(payload.start_date),
            end_date=_parse_dt(payload.end_date),
            created_by=user.id,
        )
        if sprint.start_date and sprint.end_date and sprint.start_date > sprint.end_date:
            raise HTTPException(400, 'Конец спринта не может быть раньше начала')
        session.add(sprint)
        await session.commit()
        await session.refresh(sprint)
    return JSONResponse(_sprint_to_dict(sprint), status_code=201)


async def _get_sprint(session, sprint_id: int, user):
    role_names = await get_user_role_names(user.id)
    sprint = await session.get(Sprint, sprint_id)
    if sprint is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Спринт не найден")
    workspace, role = await resolve_workspace(session, user, role_names, sprint.workspace_id)
    return sprint, workspace, role


@router.get("/{sprint_id}")
async def get_sprint(sprint_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        sprint, _, _ = await _get_sprint(session, sprint_id, user)
        tasks = (await session.execute(
            select(Task).join(SprintTask, SprintTask.task_id == Task.id)
            .where(SprintTask.sprint_id == sprint.id, Task.deleted_at.is_(None))
            .order_by(Task.id)
        )).scalars().all()
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        permissions = await request_permissions(user, sprint.workspace_id)
        visible = [
            t for t in tasks
            if task_is_visible_to_user(t, user, role_names, accessible_client_ids, permissions)
        ]
        data = _sprint_to_dict(sprint, await _progress(session, sprint))
        data["tasks"] = [{"id": t.id, "title": t.title, "status": t.status} for t in visible]
        return JSONResponse(data)


@router.patch("/{sprint_id}")
async def update_sprint(sprint_id: int, payload: SprintUpdate, user=Depends(get_current_user)):
    async with async_session() as session:
        sprint, _, _ = await _get_sprint(session, sprint_id, user)
        assert_field_writes("sprints", payload.model_dump(exclude_unset=True), sprint)
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                return JSONResponse({"error": "Название не может быть пустым"}, status_code=400)
            sprint.name = name[:200]
        if payload.goal is not None:
            sprint.goal = payload.goal[:2000] or None
        if 'start_date' in payload.model_fields_set:
            sprint.start_date = _parse_dt(payload.start_date)
        if 'end_date' in payload.model_fields_set:
            sprint.end_date = _parse_dt(payload.end_date)
        if sprint.start_date and sprint.end_date and sprint.start_date > sprint.end_date:
            raise HTTPException(400, 'Конец спринта не может быть раньше начала')
        if payload.status == 'done' and sprint.status != 'done':
            pending = (await session.execute(select(Task.id).join(SprintTask, SprintTask.task_id == Task.id).where(
                SprintTask.sprint_id == sprint.id, Task.status != 'done', Task.deleted_at.is_(None)))).scalars().all()
            if pending and payload.unfinished_policy not in ('keep', 'move'):
                raise HTTPException(409, 'Есть незавершённые задачи. Выберите: оставить в закрытом спринте или перенести.')
            if pending and payload.unfinished_policy == 'move':
                assert_field_writes('tasks', {'sprint_ids': pending})
                destination = await session.get(Sprint, payload.carryover_sprint_id) if payload.carryover_sprint_id else None
                if not destination or destination.id == sprint.id or destination.workspace_id != sprint.workspace_id or destination.status != 'active':
                    raise HTTPException(400, 'Выберите другой активный спринт этого окружения')
                await session.execute(SprintTask.__table__.delete().where(SprintTask.task_id.in_(pending),
                    SprintTask.sprint_id.in_(select(Sprint.id).where(Sprint.status == 'active'))))
                for task_id in pending:
                    session.add(SprintTask(sprint_id=destination.id, task_id=task_id))
        if payload.status is not None:
            if payload.status not in ("active", "done"):
                return JSONResponse({"error": "Статус: active или done"}, status_code=400)
            sprint.status = payload.status
        await session.commit()
        await session.refresh(sprint)
    return JSONResponse(_sprint_to_dict(sprint))


@router.delete("/{sprint_id}")
async def delete_sprint(sprint_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        sprint = await session.get(Sprint, sprint_id)
        if sprint is None:
            return JSONResponse({"error": "Спринт не найден"}, status_code=404)
        role_names = await get_user_role_names(user.id)
        _, role = await resolve_workspace(session, user, role_names, sprint.workspace_id)
        if role not in ("owner", "admin") and not user_is_superadmin(role_names):
            return JSONResponse({"error": "Удалять может админ"}, status_code=403)
        await session.execute(SprintTask.__table__.delete().where(SprintTask.sprint_id == sprint.id))
        await session.delete(sprint)
        await session.commit()
    return JSONResponse({"ok": True})


class SprintTasksPayload(BaseModel):
    task_ids: list[int]


@router.post("/{sprint_id}/tasks")
async def add_sprint_tasks(sprint_id: int, payload: SprintTasksPayload, user=Depends(get_current_user)):
    assert_field_writes("tasks", {"sprint_ids": payload.task_ids})
    async with async_session() as session:
        sprint, _, _ = await _get_sprint(session, sprint_id, user)
        tasks = (await session.execute(
            select(Task).where(Task.id.in_(payload.task_ids or []), Task.deleted_at.is_(None))
        )).scalars().all()
        role_names = await get_user_role_names(user.id)
        permissions = await request_permissions(user, sprint.workspace_id)
        accessible = await get_accessible_client_ids(session, user.id, role_names)
        if any(not task_is_visible_to_user(task, user, role_names, accessible, permissions) for task in tasks):
            raise HTTPException(403, 'Нет доступа к одной из задач')
        found = {t.id for t in tasks}
        missing = set(payload.task_ids or []) - found
        if missing:
            return JSONResponse({"error": f"Задачи не найдены: {sorted(missing)}"}, status_code=400)
        foreign = [t.id for t in tasks if (t.workspace_id or sprint.workspace_id) != sprint.workspace_id]
        if foreign:
            return JSONResponse({"error": f"Чужие задачи воркспейса: {foreign}"}, status_code=400)
        existing = {
            row[0] for row in (await session.execute(
                select(SprintTask.task_id).where(SprintTask.sprint_id == sprint.id)
            )).all()
        }
        if sprint.status != 'active':
            raise HTTPException(409, 'Добавлять задачи можно в активный спринт')
        for task in tasks:
            await session.execute(SprintTask.__table__.delete().where(
                SprintTask.task_id == task.id, SprintTask.sprint_id != sprint.id,
                SprintTask.sprint_id.in_(select(Sprint.id).where(Sprint.status == 'active'))))
        for task in tasks:
            if task.id not in existing:
                session.add(SprintTask(sprint_id=sprint.id, task_id=task.id))
        await session.commit()
    return JSONResponse({"ok": True})


@router.delete("/{sprint_id}/tasks/{task_id}")
async def remove_sprint_task(sprint_id: int, task_id: int, user=Depends(get_current_user)):
    assert_field_writes("tasks", {"sprint_ids": []})
    async with async_session() as session:
        sprint, _, _ = await _get_sprint(session, sprint_id, user)
        await session.execute(
            SprintTask.__table__.delete().where(
                SprintTask.sprint_id == sprint.id, SprintTask.task_id == task_id
            )
        )
        await session.commit()
    return JSONResponse({"ok": True})
