"""Воркспейсы, участники, спринты, пресеты, база знаний."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import (
    WS_ROLE_ADMIN,
    WS_ROLE_MEMBER,
    WS_ROLE_OWNER,
    Client,
    Note,
    Sprint,
    SprintTask,
    Task,
    User,
    Workspace,
    WorkspaceKnowledge,
    WorkspaceMember,
)
from app.core.permissions import (
    get_current_user,
    get_user_role_names,
    get_workspace_role,
    require_workspace_role,
    resolve_workspace,
    user_is_superadmin,
    workspace_role_rank,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

PRESETS: dict[str, dict] = {
    "seo": {
        "label": "SEO-команда",
        "theme": "cream",
        "dictionary": {},
        "ai_instructions": (
            "Ты аналитик SEO-команды. Отвечай по-русски, коротко и по делу: "
            "цифры, выводы, рекомендации."
        ),
    },
    "study": {
        "label": "Учёба",
        "theme": "cream",
        "dictionary": {"clients": "Проекты"},
        "ai_instructions": (
            "Ты наставник по учёбе. Отвечай по-русски, дружелюбно и конкретно: "
            "разбивай сложное на шаги, давай план и проверяй понимание."
        ),
    },
    "empty": {
        "label": "Пустой",
        "theme": None,
        "dictionary": {},
        "ai_instructions": None,
    },
}


def _ws_to_dict(ws: Workspace, role: str) -> dict:
    try:
        dictionary = json.loads(ws.dictionary or "{}")
    except (ValueError, TypeError):
        dictionary = {}
    return {
        "id": ws.id,
        "name": ws.name,
        "preset": ws.preset,
        "theme": ws.theme,
        "dictionary": dictionary,
        "has_ai_instructions": bool(ws.ai_instructions),
        "role": role,
        "created_at": ws.created_at.isoformat() if ws.created_at else None,
    }


def _member_to_dict(member: WorkspaceMember, username: str | None) -> dict:
    return {
        "user_id": member.user_id,
        "username": username,
        "role": member.role,
        "created_at": member.created_at.isoformat() if member.created_at else None,
    }


@router.get("")
async def list_workspaces(user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        if user_is_superadmin(role_names):
            workspaces = (await session.execute(select(Workspace).order_by(Workspace.id))).scalars().all()
            out = []
            for ws in workspaces:
                role = await get_workspace_role(session, user.id, ws.id) or WS_ROLE_OWNER
                out.append(_ws_to_dict(ws, role))
            return JSONResponse(out)
        rows = (await session.execute(
            select(Workspace, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user.id)
            .order_by(Workspace.id)
        )).all()
        return JSONResponse([_ws_to_dict(ws, member.role) for ws, member in rows])


class WorkspaceCreate(BaseModel):
    name: str
    preset: str = "empty"


@router.post("", status_code=201)
async def create_workspace(payload: WorkspaceCreate, user=Depends(get_current_user)):
    name = (payload.name or "").strip()
    if not name:
        return JSONResponse({"error": "Нужно название"}, status_code=400)
    preset = PRESETS.get(payload.preset, PRESETS["empty"])
    async with async_session() as session:
        ws = Workspace(
            name=name[:200],
            preset=payload.preset if payload.preset in PRESETS else "empty",
            theme=preset["theme"],
            dictionary=json.dumps(preset["dictionary"], ensure_ascii=False),
            ai_instructions=preset["ai_instructions"],
            created_by=user.id,
        )
        session.add(ws)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WS_ROLE_OWNER))
        if payload.preset == "study":
            session.add(Sprint(
                workspace_id=ws.id,
                name="Первая неделя",
                goal="Освоиться и закрыть первые учебные задачи",
                status="active",
                created_by=user.id,
            ))
        await session.commit()
        await session.refresh(ws)
    return JSONResponse(_ws_to_dict(ws, WS_ROLE_OWNER), status_code=201)


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, role = await resolve_workspace(session, user, role_names, workspace_id)
        data = _ws_to_dict(workspace, role)
        data["ai_instructions"] = workspace.ai_instructions or ""
        return JSONResponse(data)


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    theme: str | None = None
    dictionary: dict | None = None
    ai_instructions: str | None = None


@router.patch("/{workspace_id}")
async def update_workspace(workspace_id: int, payload: WorkspaceUpdate, ctx=Depends(require_workspace_role("owner", "admin"))):
    workspace = ctx["workspace"]
    async with async_session() as session:
        ws = await session.get(Workspace, workspace.id)
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                return JSONResponse({"error": "Название не может быть пустым"}, status_code=400)
            ws.name = name[:200]
        if payload.theme is not None:
            if payload.theme not in (None, "", "cream", "graphite"):
                return JSONResponse({"error": "Неизвестная тема"}, status_code=400)
            ws.theme = payload.theme or None
        if payload.dictionary is not None:
            if not isinstance(payload.dictionary, dict):
                return JSONResponse({"error": "Словарь должен быть объектом"}, status_code=400)
            clean = {str(k)[:40]: str(v)[:40] for k, v in payload.dictionary.items()}
            ws.dictionary = json.dumps(clean, ensure_ascii=False)
        if payload.ai_instructions is not None:
            ws.ai_instructions = payload.ai_instructions[:10000] or None
        await session.commit()
        await session.refresh(ws)
        role = await get_workspace_role(session, ctx["user"].id, ws.id) or ctx["role"]
    return JSONResponse(_ws_to_dict(ws, role))


@router.delete("/{workspace_id}")
async def delete_workspace(workspace_id: int, ctx=Depends(require_workspace_role("owner"))):
    user = ctx["user"]
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, role = await resolve_workspace(session, user, role_names, workspace_id)
        if role != WS_ROLE_OWNER and not user_is_superadmin(role_names):
            return JSONResponse({"error": "Удалять может только владелец"}, status_code=403)
        wid = workspace.id
        # Каскад вручную (работает и на sqlite без FK-enforcement)
        await session.execute(SprintTask.__table__.delete().where(
            SprintTask.sprint_id.in_(select(Sprint.id).where(Sprint.workspace_id == wid))))
        for model, column in ((Sprint, Sprint.workspace_id), (Task, Task.workspace_id),
                              (Client, Client.workspace_id), (Note, Note.workspace_id),
                              (WorkspaceKnowledge, WorkspaceKnowledge.workspace_id),
                              (WorkspaceMember, WorkspaceMember.workspace_id)):
            await session.execute(model.__table__.delete().where(column == wid))
        await session.execute(Workspace.__table__.delete().where(Workspace.id == wid))
        await session.commit()
    return JSONResponse({"ok": True})


@router.get("/{workspace_id}/members")
async def list_members(workspace_id: int, ctx=Depends(require_workspace_role("owner", "admin", "member"))):
    async with async_session() as session:
        rows = (await session.execute(
            select(WorkspaceMember, User.username)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == ctx["workspace"].id)
            .order_by(User.username)
        )).all()
        return JSONResponse([_member_to_dict(m, username) for m, username in rows])


class MemberCreate(BaseModel):
    user_id: int
    role: str = WS_ROLE_MEMBER


def _can_manage(actor_role: str, actor_is_super: bool, target_role: str | None, new_role: str | None = None) -> str | None:
    """Возвращает текст ошибки или None если можно."""
    if actor_is_super:
        return None
    if target_role == WS_ROLE_OWNER:
        return "Владельца может менять только суперадмин"
    if actor_role not in (WS_ROLE_OWNER, WS_ROLE_ADMIN):
        return "Недостаточно прав в воркспейсе"
    if new_role == WS_ROLE_OWNER:
        return "Назначить владельцем может только суперадмин"
    return None


@router.post("/{workspace_id}/members", status_code=201)
async def add_member(workspace_id: int, payload: MemberCreate, ctx=Depends(require_workspace_role("owner", "admin"))):
    if payload.role not in (WS_ROLE_ADMIN, WS_ROLE_MEMBER):
        return JSONResponse({"error": "Роль: admin или member"}, status_code=400)
    async with async_session() as session:
        role_names = await get_user_role_names(ctx["user"].id)
        actor_is_super = user_is_superadmin(role_names)
        err = _can_manage(ctx["role"], actor_is_super, None, payload.role)
        if err:
            return JSONResponse({"error": err}, status_code=403)
        target = await session.get(User, payload.user_id)
        if target is None:
            return JSONResponse({"error": "Пользователь не найден"}, status_code=404)
        existing = (await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx["workspace"].id,
                WorkspaceMember.user_id == payload.user_id,
            )
        )).scalar_one_or_none()
        if existing:
            return JSONResponse({"error": "Уже участник"}, status_code=400)
        member = WorkspaceMember(workspace_id=ctx["workspace"].id, user_id=payload.user_id, role=payload.role)
        session.add(member)
        await session.commit()
        await session.refresh(member)
    return JSONResponse(_member_to_dict(member, target.username), status_code=201)


class MemberUpdate(BaseModel):
    role: str


@router.patch("/{workspace_id}/members/{user_id}")
async def update_member(workspace_id: int, user_id: int, payload: MemberUpdate, ctx=Depends(require_workspace_role("owner", "admin"))):
    async with async_session() as session:
        role_names = await get_user_role_names(ctx["user"].id)
        actor_is_super = user_is_superadmin(role_names)
        if payload.role not in (WS_ROLE_ADMIN, WS_ROLE_MEMBER) and not (
            payload.role == WS_ROLE_OWNER and actor_is_super
        ):
            return JSONResponse({"error": "Роль: admin или member"}, status_code=400)
        member = (await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx["workspace"].id,
                WorkspaceMember.user_id == user_id,
            )
        )).scalar_one_or_none()
        if member is None:
            return JSONResponse({"error": "Не участник"}, status_code=404)
        err = _can_manage(ctx["role"], actor_is_super, member.role, payload.role)
        if err:
            return JSONResponse({"error": err}, status_code=403)
        member.role = payload.role
        await session.commit()
        username = (await session.get(User, user_id)).username
    return JSONResponse(_member_to_dict(member, username))


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(workspace_id: int, user_id: int, ctx=Depends(require_workspace_role("owner", "admin"))):
    async with async_session() as session:
        role_names = await get_user_role_names(ctx["user"].id)
        actor_is_super = user_is_superadmin(role_names)
        member = (await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx["workspace"].id,
                WorkspaceMember.user_id == user_id,
            )
        )).scalar_one_or_none()
        if member is None:
            return JSONResponse({"error": "Не участник"}, status_code=404)
        err = _can_manage(ctx["role"], actor_is_super, member.role)
        if err:
            return JSONResponse({"error": err}, status_code=403)
        await session.delete(member)
        await session.commit()
    return JSONResponse({"ok": True})


@router.get("/{workspace_id}/knowledge")
async def list_knowledge(workspace_id: int, ctx=Depends(require_workspace_role("owner", "admin", "member"))):
    async with async_session() as session:
        rows = (await session.execute(
            select(WorkspaceKnowledge).where(WorkspaceKnowledge.workspace_id == ctx["workspace"].id)
            .order_by(WorkspaceKnowledge.id.desc()).limit(200)
        )).scalars().all()
        return JSONResponse([{
            "id": r.id, "fact": r.fact,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows])


class KnowledgeCreate(BaseModel):
    fact: str


@router.post("/{workspace_id}/knowledge", status_code=201)
async def add_knowledge(workspace_id: int, payload: KnowledgeCreate, ctx=Depends(require_workspace_role("owner", "admin"))):
    fact = (payload.fact or "").strip()
    if not fact:
        return JSONResponse({"error": "Пустой факт"}, status_code=400)
    async with async_session() as session:
        row = WorkspaceKnowledge(workspace_id=ctx["workspace"].id, fact=fact[:2000], created_by=ctx["user"].id)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return JSONResponse({"id": row.id, "fact": row.fact}, status_code=201)


@router.delete("/{workspace_id}/knowledge/{fact_id}")
async def delete_knowledge(workspace_id: int, fact_id: int, ctx=Depends(require_workspace_role("owner", "admin"))):
    async with async_session() as session:
        row = await session.get(WorkspaceKnowledge, fact_id)
        if row is None or row.workspace_id != ctx["workspace"].id:
            return JSONResponse({"error": "Не найдено"}, status_code=404)
        await session.delete(row)
        await session.commit()
    return JSONResponse({"ok": True})


def workspace_fact_block(workspace: Workspace | None, knowledge: list[str]) -> str:
    parts = []
    if workspace is not None and (workspace.ai_instructions or "").strip():
        parts.append(f"Инструкции воркспейса «{workspace.name}»: {(workspace.ai_instructions or '').strip()}")
    if knowledge:
        parts.append("Память воркспейса:\n" + "\n".join(f"- {fact}" for fact in knowledge[:20]))
    return "\n".join(parts)


async def workspace_context(session, workspace_id: int | None) -> tuple[Workspace | None, list[str]]:
    if workspace_id is None:
        return None, []
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        return None, []
    rows = (await session.execute(
        select(WorkspaceKnowledge.fact).where(WorkspaceKnowledge.workspace_id == ws.id)
        .order_by(WorkspaceKnowledge.id.desc()).limit(20)
    )).scalars().all()
    return ws, list(rows)
