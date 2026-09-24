"""Спринты: отрезок времени + набор задач + прогресс."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import Sprint, SprintTask, Task
from app.core.permissions import get_current_user, get_user_role_names, resolve_workspace, user_is_superadmin

router = APIRouter(prefix="/api/sprints", tags=["sprints"])


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


async def _progress(session, sprint: Sprint) -> dict:
    rows = (await session.execute(
        select(Task.status).join(SprintTask, SprintTask.task_id == Task.id)
        .where(SprintTask.sprint_id == sprint.id, Task.deleted_at.is_(None))
    )).scalars().all()
    total = len(rows)
    done = sum(1 for status in rows if status == "done")
    return {"total": total, "done": done, "percent": round(done / total * 100) if total else 0}


def _sprint_to_dict(sprint: Sprint, progress: dict | None = None) -> dict:
    return {
        "id": sprint.id,
        "workspace_id": sprint.workspace_id,
        "name": sprint.name,
        "goal": sprint.goal or "",
        "start_date": sprint.start_date.date().isoformat() if sprint.start_date else None,
        "end_date": sprint.end_date.date().isoformat() if sprint.end_date else None,
        "status": sprint.status,
        "progress": progress or {"total": 0, "done": 0, "percent": 0},
        "created_at": sprint.created_at.isoformat() if sprint.created_at else None,
    }


class SprintCreate(BaseModel):
    name: str
    goal: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class SprintUpdate(BaseModel):
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
        data = _sprint_to_dict(sprint, await _progress(session, sprint))
        data["tasks"] = [{"id": t.id, "title": t.title, "status": t.status} for t in tasks]
        return JSONResponse(data)


@router.patch("/{sprint_id}")
async def update_sprint(sprint_id: int, payload: SprintUpdate, user=Depends(get_current_user)):
    async with async_session() as session:
        sprint, _, _ = await _get_sprint(session, sprint_id, user)
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                return JSONResponse({"error": "Название не может быть пустым"}, status_code=400)
            sprint.name = name[:200]
        if payload.goal is not None:
            sprint.goal = payload.goal[:2000] or None
        if payload.start_date is not None:
            sprint.start_date = _parse_dt(payload.start_date)
        if payload.end_date is not None:
            sprint.end_date = _parse_dt(payload.end_date)
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
    async with async_session() as session:
        sprint, _, _ = await _get_sprint(session, sprint_id, user)
        tasks = (await session.execute(
            select(Task).where(Task.id.in_(payload.task_ids or []), Task.deleted_at.is_(None))
        )).scalars().all()
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
        for task in tasks:
            if task.id not in existing:
                session.add(SprintTask(sprint_id=sprint.id, task_id=task.id))
        await session.commit()
    return JSONResponse({"ok": True})


@router.delete("/{sprint_id}/tasks/{task_id}")
async def remove_sprint_task(sprint_id: int, task_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        sprint, _, _ = await _get_sprint(session, sprint_id, user)
        await session.execute(
            SprintTask.__table__.delete().where(
                SprintTask.sprint_id == sprint.id, SprintTask.task_id == task_id
            )
        )
        await session.commit()
    return JSONResponse({"ok": True})
