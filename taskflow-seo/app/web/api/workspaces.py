"""Воркспейсы, участники, спринты, пресеты, база знаний."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, Request
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
    WorkspaceRemoval,
    WorkspaceRole,
)
from app.core.permissions import (
    get_current_user,
    get_user_permissions,
    require_workspace_management,
    require_root,
    get_user_role_names,
    get_workspace_role,
    is_root_user,
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
        "welcome_sprint": {"name": "Неделя 1: старт", "goal": "Освоиться, разбить обучение на задачи и закрыть первые шаги"},
    },
    "project": {
        "label": "Проект",
        "theme": "cream",
        "dictionary": {"clients": "Проекты"},
        "ai_instructions": (
            "Ты помощник команды разработки. Отвечай по-русски, конкретно и по делу: "
            "фичи разбивай на задачи, сроки оценивай честно, риски называй прямо."
        ),
        "welcome_sprint": {"name": "Спринт 1: MVP", "goal": "Собрать минимальный продукт: основные функции, первые задачи команде"},
    },
    "empty": {
        "label": "Пустой",
        "theme": None,
        "dictionary": {},
        "ai_instructions": None,
    },
}


def _parse_ui_config(raw) -> dict:
    try:
        data = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _sanitize_ui_config(raw: dict) -> dict:
    """Чистит конфиг оформления: только известные секции, лимиты длины."""
    clean: dict = {}
    for section in ('tasks', 'sprints'):
        order = raw.get(section, {}).get('order') if isinstance(raw.get(section), dict) else None
        if isinstance(order, list):
            clean[section] = {'order': list(dict.fromkeys(x for x in order if isinstance(x, str) and len(x) <= 40))[:40]}

    nav = raw.get("nav")
    if isinstance(nav, dict):
        items = {}
        for route, item in list(nav.items())[:40]:
            if not isinstance(route, str) or not route.startswith("/") or len(route) > 40:
                continue
            if not isinstance(item, dict):
                continue
            entry: dict = {}
            label = item.get("label")
            if isinstance(label, str) and label.strip():
                entry["label"] = label.strip()[:40]
            hint = item.get("hint")
            if isinstance(hint, str) and hint.strip():
                entry["hint"] = hint.strip()[:80]
            if item.get("visible") is False:
                entry["visible"] = False
            if entry:
                items[route] = entry
        if items:
            clean["nav"] = items
    titles = raw.get("titles")
    if isinstance(titles, dict):
        items = {}
        for route, title in list(titles.items())[:40]:
            if isinstance(route, str) and isinstance(title, str) and title.strip():
                items[route] = title.strip()[:60]
        if items:
            clean["titles"] = items
    for section in ("tasks", "sprints"):
        fields = raw.get(section)
        if not isinstance(fields, dict):
            continue
        fields = fields.get("fields")
        if not isinstance(fields, dict):
            continue
        items = {}
        for key, item in list(fields.items())[:40]:
            if not isinstance(key, str) or len(key) > 40 or not isinstance(item, dict):
                continue
            entry = {}
            label = item.get("label")
            if isinstance(label, str) and label.strip():
                entry["label"] = label.strip()[:60]
            if item.get("visible") is False:
                entry["visible"] = False
            if entry:
                items[key] = entry
        if items:
            clean.setdefault(section, {})["fields"] = items
    return clean


def _ws_to_dict(ws: Workspace, role: str) -> dict:
    try:
        dictionary = json.loads(ws.dictionary or "{}")
    except (ValueError, TypeError):
        dictionary = {}
    return {
        "id": ws.id,
        "name": ws.name,
        "preset": ws.preset,
        "visibility": ws.visibility,
        "enabled_modules": json.loads(ws.enabled_modules or "[]"),
        "theme": "cream" if ws.theme == "glass" else ws.theme,
        "dictionary": dictionary,
        "has_ai_instructions": bool(ws.ai_instructions),
        "ui_config": _parse_ui_config(ws.ui_config),
        "role": role,
        "created_at": ws.created_at.isoformat() if ws.created_at else None,
        "deleted_at": ws.deleted_at.isoformat() if ws.deleted_at else None,
    }


async def _purge_task(session, task_id: int) -> None:
    from sqlalchemy import delete, update, or_
    from app.core.models import (TaskComment, TaskCoExecutor, TaskDependency, SprintTask, CrmDeal,
                                Notification, Reminder, FileAttachment, task_tags)
    for model, condition in (
        (TaskComment, TaskComment.task_id == task_id), (TaskCoExecutor, TaskCoExecutor.task_id == task_id),
        (SprintTask, SprintTask.task_id == task_id),
        (TaskDependency, or_(TaskDependency.task_id == task_id, TaskDependency.depends_on_id == task_id)),
        (Notification, Notification.task_id == task_id), (Reminder, Reminder.task_id == task_id),
        (FileAttachment, FileAttachment.task_id == task_id),
    ):
        await session.execute(delete(model).where(condition))
    await session.execute(task_tags.delete().where(task_tags.c.task_id == task_id))
    await session.execute(update(CrmDeal).where(CrmDeal.task_id == task_id).values(task_id=None))
    await session.execute(update(Task).where(Task.recurring_parent_id == task_id).values(recurring_parent_id=None))
    await session.execute(delete(Task).where(Task.id == task_id))


async def _purge_client(session, client_id: int) -> None:
    from sqlalchemy import delete, update, or_
    from app.core.models import (ClientContact, Contract, FileAttachment, CrmDeal, CrmContact,
        Notification, Reminder, GeneratedReport, ClientResponsible, UserClientAccess, Page, Module)
    tasks = (await session.execute(select(Task.id).where(Task.client_id == client_id))).scalars().all()
    for task_id in tasks:
        await _purge_task(session, task_id)
    contracts = select(Contract.id).where(Contract.client_id == client_id)
    await session.execute(update(Task).where(Task.contract_id.in_(contracts)).values(contract_id=None))
    await session.execute(update(CrmDeal).where(CrmDeal.contract_id.in_(contracts)).values(contract_id=None))
    await session.execute(update(CrmDeal).where(CrmDeal.client_id == client_id).values(client_id=None))
    await session.execute(update(CrmContact).where(CrmContact.client_id == client_id).values(client_id=None))
    await session.execute(update(Module).where(Module.client_id == client_id).values(client_id=None))
    for model, condition in (
        (FileAttachment, or_(FileAttachment.client_id == client_id, FileAttachment.contract_id.in_(contracts))),
        (Notification, Notification.client_id == client_id), (Reminder, Reminder.client_id == client_id),
        (GeneratedReport, GeneratedReport.client_id == client_id), (Page, Page.client_id == client_id),
        (ClientResponsible, ClientResponsible.client_id == client_id), (UserClientAccess, UserClientAccess.client_id == client_id),
        (Contract, Contract.client_id == client_id), (ClientContact, ClientContact.client_id == client_id),
    ):
        await session.execute(delete(model).where(condition))
    await session.execute(delete(Client).where(Client.id == client_id))


async def _purge_workspace(session, workspace_id: int) -> None:
    """Delete dependencies explicitly on SQLite and PostgreSQL, children first."""
    from sqlalchemy import delete, update, or_
    from app.core.models import (ClientContact, Contract, FileAttachment, TaskComment, WorkspaceKnowledge,
        CrmDeal, CrmActivity, CrmContact, CrmPipeline, CrmField, Module, Cycle, QuickTaskTemplate,
        TaskCoExecutor, TaskDependency, Notification, Reminder, GeneratedReport, ClientResponsible,
        UserClientAccess, Page, FeatureOverride, task_tags)
    tasks = select(Task.id).where(Task.workspace_id == workspace_id)
    clients = select(Client.id).where(Client.workspace_id == workspace_id)
    modules = select(Module.id).where(Module.workspace_id == workspace_id)
    contracts = select(Contract.id).where(Contract.client_id.in_(clients))
    await session.execute(update(Task).where(Task.crm_deal_id.in_(select(CrmDeal.id).where(CrmDeal.workspace_id == workspace_id))).values(crm_deal_id=None))
    for model in (CrmActivity, CrmDeal, CrmContact, CrmPipeline, CrmField):
        await session.execute(delete(model).where(model.workspace_id == workspace_id))
    for model, condition in (
        (TaskComment, TaskComment.task_id.in_(tasks)),
        (TaskCoExecutor, TaskCoExecutor.task_id.in_(tasks)),
        (TaskDependency, or_(TaskDependency.task_id.in_(tasks), TaskDependency.depends_on_id.in_(tasks))),
        (FileAttachment, or_(FileAttachment.task_id.in_(tasks), FileAttachment.client_id.in_(clients), FileAttachment.contract_id.in_(contracts))),
        (Notification, or_(Notification.task_id.in_(tasks), Notification.client_id.in_(clients))),
        (Reminder, or_(Reminder.task_id.in_(tasks), Reminder.client_id.in_(clients))),
        (GeneratedReport, GeneratedReport.client_id.in_(clients)),
        (ClientResponsible, ClientResponsible.client_id.in_(clients)),
        (UserClientAccess, UserClientAccess.client_id.in_(clients)),
        (Page, or_(Page.client_id.in_(clients), Page.module_id.in_(modules))),
        (QuickTaskTemplate, QuickTaskTemplate.workspace_id == workspace_id),
        (SprintTask, or_(SprintTask.task_id.in_(tasks), SprintTask.sprint_id.in_(select(Sprint.id).where(Sprint.workspace_id == workspace_id)))),
        (Contract, Contract.client_id.in_(clients)), (ClientContact, ClientContact.client_id.in_(clients)),
        (WorkspaceRemoval, WorkspaceRemoval.workspace_id == workspace_id),
        (WorkspaceMember, WorkspaceMember.workspace_id == workspace_id),
        (WorkspaceRole, WorkspaceRole.workspace_id == workspace_id),
        (FeatureOverride, (FeatureOverride.scope == 'workspace') & (FeatureOverride.target_id == workspace_id)),
    ):
        await session.execute(delete(model).where(condition))
    await session.execute(task_tags.delete().where(task_tags.c.task_id.in_(tasks)))
    # SET NULL references also detach explicitly when SQLite FK enforcement is disabled.
    await session.execute(update(Task).where(Task.recurring_parent_id.in_(tasks)).values(recurring_parent_id=None))
    await session.execute(update(Task).where(Task.contract_id.in_(contracts)).values(contract_id=None))
    for model, column in ((Sprint, Sprint.workspace_id), (Task, Task.workspace_id),
                          (Cycle, Cycle.module_id), (Module, Module.workspace_id),
                          (Client, Client.workspace_id), (Note, Note.workspace_id),
                          (WorkspaceKnowledge, WorkspaceKnowledge.workspace_id)):
        condition = column.in_(modules) if model is Cycle else column == workspace_id
        await session.execute(delete(model).where(condition))
    await session.execute(delete(Workspace).where(Workspace.id == workspace_id))


def _member_to_dict(member: WorkspaceMember, username: str | None, custom_role: str | None = None) -> dict:
    return {
        "user_id": member.user_id,
        "username": username,
        "role": member.role,
        "custom_role_id": member.custom_role_id,
        "custom_role": custom_role,
        "created_at": member.created_at.isoformat() if member.created_at else None,
    }


@router.get("")
async def list_workspaces(deleted: bool = Query(default=False), user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        if user_is_superadmin(role_names):
            stmt = select(Workspace).order_by(Workspace.id)
            stmt = stmt.where(Workspace.deleted_at.is_not(None) if deleted else Workspace.deleted_at.is_(None))
            workspaces = (await session.execute(stmt)).scalars().all()
            out = []
            for ws in workspaces:
                role = await get_workspace_role(session, user.id, ws.id) or WS_ROLE_OWNER
                out.append(_ws_to_dict(ws, role))
            return JSONResponse(out)
        stmt = (
            select(Workspace, WorkspaceMember)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user.id)
        )
        stmt = stmt.where(Workspace.deleted_at.is_not(None) if deleted else Workspace.deleted_at.is_(None))
        rows = (await session.execute(stmt.order_by(Workspace.id))).all()
        return JSONResponse([_ws_to_dict(ws, member.role) for ws, member in rows])


class WorkspaceCreate(BaseModel):
    name: str
    preset: str = "empty"
    visibility: str = "hidden"


@router.post("", status_code=201)
async def create_workspace(payload: WorkspaceCreate, user=Depends(get_current_user)):
    name = (payload.name or "").strip()
    if not name:
        return JSONResponse({"error": "Нужно название"}, status_code=400)
    if payload.visibility not in ('open', 'closed', 'hidden'):
        raise HTTPException(status_code=400, detail='Неизвестная видимость')
    preset = PRESETS.get(payload.preset, PRESETS["empty"])
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        from app.core.permissions import is_feature_available
        if not (is_root_user(user) or (permissions.get('workspaces_create') and await is_feature_available(user, 'workspaces_create'))):
            raise HTTPException(status_code=403, detail='Нет права создавать пространства')
        from app.core.workspace_modules import PRESET_MODULES
        ws = Workspace(
            name=name[:200],
            preset=payload.preset if payload.preset in PRESETS else "empty",
            theme=preset["theme"],
            dictionary=json.dumps(preset["dictionary"], ensure_ascii=False),
            ai_instructions=preset["ai_instructions"],
            created_by=user.id,
            visibility=payload.visibility,
            enabled_modules=json.dumps(PRESET_MODULES.get(payload.preset, PRESET_MODULES['empty'])),
        )
        session.add(ws)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WS_ROLE_OWNER))
        welcome = preset.get("welcome_sprint")
        if isinstance(welcome, dict) and welcome.get("name"):
            session.add(Sprint(
                workspace_id=ws.id,
                name=str(welcome["name"])[:200],
                goal=str(welcome.get("goal") or "")[:2000] or None,
                status="active",
                created_by=user.id,
            ))
        await session.commit()
        await session.refresh(ws)
    return JSONResponse(_ws_to_dict(ws, WS_ROLE_OWNER), status_code=201)


@router.get("/presets/list")
async def list_presets(user=Depends(get_current_user)):
    return JSONResponse([
        {"id": key, "label": value["label"]}
        for key, value in PRESETS.items()
    ])


@router.get('/directory/list')
async def space_directory(user=Depends(get_current_user)):
    async with async_session() as session:
        rows = (await session.execute(select(Workspace).where(
            Workspace.deleted_at.is_(None), Workspace.visibility.in_(['open', 'closed'])).order_by(Workspace.name))).scalars().all()
        return [{'id': ws.id, 'name': ws.name, 'visibility': ws.visibility,
                 'joined': await get_workspace_role(session, user.id, ws.id) is not None} for ws in rows]


@router.post('/{workspace_id}/join')
async def join_space(workspace_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        ws = await session.get(Workspace, workspace_id)
        if not ws or ws.deleted_at is not None or ws.visibility == 'hidden':
            raise HTTPException(status_code=404, detail='Пространство не найдено')
        if ws.visibility != 'open':
            raise HTTPException(status_code=403, detail='Запросите приглашение у администратора пространства')
        if not await get_workspace_role(session, user.id, ws.id):
            session.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role='member'))
        await session.commit()
    return {'ok': True}


@router.get('/{workspace_id}/modules')
async def space_modules(workspace_id: int, user=Depends(get_current_user)):
    from app.core.workspace_modules import MODULES
    async with async_session() as session:
        ws, _ = await resolve_workspace(session, user, await get_user_role_names(user.id), workspace_id)
        return {'catalog': MODULES, 'enabled': json.loads(ws.enabled_modules or '[]')}


@router.put('/{workspace_id}/modules')
async def set_space_modules(workspace_id: int, request: Request, user=Depends(require_root())):
    from app.core.workspace_modules import MODULES
    data = await request.json()
    enabled = data.get('enabled')
    if not isinstance(enabled, list) or any(not isinstance(x, str) or x not in MODULES for x in enabled):
        raise HTTPException(status_code=400, detail='Передайте список известных модулей')
    async with async_session() as session:
        ws = await session.get(Workspace, workspace_id)
        if not ws or ws.deleted_at is not None:
            raise HTTPException(status_code=404, detail='Пространство не найдено')
        from app.core.models import FeatureOverride
        from app.core.workspace_modules import module_for_permission
        from app.core.permission_catalog import work_scope_keys
        removed = set(json.loads(ws.enabled_modules or '[]')) - set(enabled)
        for key in work_scope_keys():
            if module_for_permission(key) in removed:
                override = (await session.execute(select(FeatureOverride).where(FeatureOverride.scope == 'workspace', FeatureOverride.target_id == ws.id, FeatureOverride.key == key))).scalars().first()
                if override:
                    override.enabled = False
                else:
                    session.add(FeatureOverride(scope='workspace', target_id=ws.id, key=key, enabled=False))
        ws.enabled_modules = json.dumps(list(dict.fromkeys(enabled)))
        await session.commit()
    from app.core.cache import dashboard_cache
    dashboard_cache.clear()
    return {'ok': True}


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, role = await resolve_workspace(session, user, role_names, workspace_id)
        data = _ws_to_dict(workspace, role)
        data["ai_instructions"] = workspace.ai_instructions or ""
        from app.core.access_policy import field_access
        data["field_access"] = await field_access(user, workspace_id)
        from app.core.permissions import request_permissions
        data["permissions"] = await request_permissions(user, workspace_id)
        return JSONResponse(data)


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    theme: str | None = None
    dictionary: dict | None = None
    ai_instructions: str | None = None
    ui_config: dict | None = None
    visibility: str | None = None


@router.patch("/{workspace_id}")
async def update_workspace(workspace_id: int, payload: WorkspaceUpdate, ctx=Depends(require_workspace_management("workspace_settings"))):
    workspace = ctx["workspace"]
    async with async_session() as session:
        ws = await session.get(Workspace, workspace.id)
        if payload.visibility is not None:
            if payload.visibility not in ('open', 'closed', 'hidden'):
                raise HTTPException(status_code=400, detail='Неизвестная видимость')
            ws.visibility = payload.visibility
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
        if payload.ui_config is not None:
            if not isinstance(payload.ui_config, dict):
                return JSONResponse({"error": "ui_config должен быть объектом"}, status_code=400)
            if len(json.dumps(payload.ui_config, ensure_ascii=False)) > 50000:
                return JSONResponse({"error": "Слишком большой ui_config"}, status_code=400)
            raw = json.dumps(_sanitize_ui_config(payload.ui_config), ensure_ascii=False)
            ws.ui_config = raw
        await session.commit()
        await session.refresh(ws)
        role = await get_workspace_role(session, ctx["user"].id, ws.id) or ctx["role"]
    return JSONResponse(_ws_to_dict(ws, role))


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: int,
    permanent: bool = Query(default=False),
    user=Depends(get_current_user),
):
    from app.core.utils.timezone import utc_now
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, role = await resolve_workspace(session, user, role_names, workspace_id, allow_deleted=True)
        if role != WS_ROLE_OWNER and not user_is_superadmin(role_names):
            return JSONResponse({"error": "Удалять может только владелец"}, status_code=403)
        # Каскад вручную (работает и на sqlite без FK-enforcement)
        ws = await session.get(Workspace, workspace.id)
        if permanent:
            await _purge_workspace(session, ws.id)
            await session.commit()
            return JSONResponse({"ok": True, "permanent": True})
        ws.deleted_at = utc_now()
        await session.commit()
    return JSONResponse({"ok": True, "permanent": False})


@router.post("/{workspace_id}/restore")
async def restore_workspace(workspace_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        workspace, role = await resolve_workspace(session, user, role_names, workspace_id, allow_deleted=True)
        if role != WS_ROLE_OWNER and not user_is_superadmin(role_names):
            return JSONResponse({"error": "Восстанавливать может только владелец"}, status_code=403)
        ws = await session.get(Workspace, workspace.id)
        ws.deleted_at = None
        await session.commit()
    return JSONResponse({"ok": True})


@router.get("/{workspace_id}/members")
async def list_members(workspace_id: int, ctx=Depends(require_workspace_role("owner", "admin", "member"))):
    async with async_session() as session:
        rows = (await session.execute(
            select(WorkspaceMember, User.username, WorkspaceRole.name)
            .join(User, User.id == WorkspaceMember.user_id)
            .outerjoin(WorkspaceRole, WorkspaceRole.id == WorkspaceMember.custom_role_id)
            .where(WorkspaceMember.workspace_id == ctx["workspace"].id)
            .order_by(User.username)
        )).all()
        return JSONResponse([
            _member_to_dict(m, username, custom_role)
            for m, username, custom_role in rows
        ])


class MemberCreate(BaseModel):
    user_id: int | None = None
    username: str | None = None
    role: str = WS_ROLE_MEMBER


def _can_manage(actor_role: str, actor_is_super: bool, target_role: str | None, new_role: str | None = None) -> str | None:
    """Возвращает текст ошибки или None если можно."""
    if actor_is_super:
        return None
    if target_role == WS_ROLE_OWNER:
        return "Владельца может менять только суперадмин"
    if actor_role == WS_ROLE_OWNER:
        if new_role == WS_ROLE_OWNER:
            return "Назначить владельцем может только суперадмин"
        return None
    if actor_role == WS_ROLE_ADMIN:
        # Администратор окружения управляет только участниками ниже себя.
        # Равные администраторы и повышение до администратора — зона владельца.
        if target_role not in (None, WS_ROLE_MEMBER):
            return "Администратор окружения может управлять только участниками"
        if new_role == WS_ROLE_ADMIN:
            return "Назначать администраторов может только владелец окружения"
        return None
    return "Недостаточно прав в воркспейсе"


async def _owner_count(session, workspace_id: int) -> int:
    from sqlalchemy import func
    return (await session.execute(
        select(func.count(WorkspaceMember.id)).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == WS_ROLE_OWNER,
        )
    )).scalar() or 0


async def _can_leave_ownership(session, workspace_id: int, actor_id: int, target_id: int) -> str | None:
    """Владелец может сложить полномочия/выйти, только если останется другой владелец.

    Иначе окружение станет бесхозным: никто не сможет управлять составом и удалением.
    """
    if actor_id != target_id:
        return "Владельца может менять только суперадмин"
    if await _owner_count(session, workspace_id) < 2:
        return "Нельзя: вы единственный владелец. Сначала передайте владение другому участнику"
    return None


@router.post("/{workspace_id}/members", status_code=201)
async def add_member(workspace_id: int, payload: MemberCreate, ctx=Depends(require_workspace_management("workspace_members"))):
    if payload.role not in (WS_ROLE_ADMIN, WS_ROLE_MEMBER):
        return JSONResponse({"error": "Роль: admin или member"}, status_code=400)
    async with async_session() as session:
        role_names = await get_user_role_names(ctx["user"].id)
        actor_is_super = user_is_superadmin(role_names)
        err = _can_manage(ctx["role"], actor_is_super, None, payload.role)
        if err:
            return JSONResponse({"error": err}, status_code=403)
        if payload.username:
            target = (await session.execute(select(User).where(User.username == payload.username.strip()))).scalar_one_or_none()
            payload.user_id = target.id if target else None
        else:
            target = await session.get(User, payload.user_id) if payload.user_id else None
        if target is None or not target.is_active:
            return JSONResponse({"error": "Пользователь не найден"}, status_code=404)
        existing = (await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx["workspace"].id,
                WorkspaceMember.user_id == payload.user_id,
            )
        )).scalar_one_or_none()
        if existing:
            return JSONResponse({"error": "Уже участник"}, status_code=400)
        if not actor_is_super:
            from app.core.permission_catalog import workspace_default_permissions
            from app.core.permissions import get_workspace_permissions, assert_within_ceiling
            from app.core.access_policy import assert_field_ceiling
            assert_within_ceiling(await get_workspace_permissions(ctx['user'].id, workspace_id) or {}, workspace_default_permissions(payload.role))
            await assert_field_ceiling(ctx['user'], workspace_id, {})
        member = WorkspaceMember(workspace_id=ctx["workspace"].id, user_id=payload.user_id, role=payload.role)
        session.add(member)
        # повторное приглашение стирает tombstone явного удаления
        await session.execute(
            WorkspaceRemoval.__table__.delete().where(
                WorkspaceRemoval.workspace_id == ctx["workspace"].id,
                WorkspaceRemoval.user_id == payload.user_id,
            )
        )
        await session.commit()
        await session.refresh(member)
    return JSONResponse(_member_to_dict(member, target.username), status_code=201)


class MemberUpdate(BaseModel):
    role: str


@router.patch("/{workspace_id}/members/{user_id}")
async def update_member(workspace_id: int, user_id: int, payload: MemberUpdate, ctx=Depends(require_workspace_management("workspace_members"))):
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
        target = await session.get(User, user_id)
        if target is not None and target.is_root and not is_root_user(ctx["user"]):
            return JSONResponse({"error": "Нельзя изменять root-пользователя"}, status_code=403)
        if member.role == WS_ROLE_OWNER and payload.role != WS_ROLE_OWNER and not actor_is_super:
            err = await _can_leave_ownership(session, ctx["workspace"].id, ctx["user"].id, user_id)
        else:
            err = _can_manage(ctx["role"], actor_is_super, member.role, payload.role)
        if err:
            return JSONResponse({"error": err}, status_code=403)
        if not actor_is_super and not member.custom_role_id:
            from app.core.permission_catalog import workspace_default_permissions
            from app.core.permissions import get_workspace_permissions, assert_within_ceiling
            candidate = {**workspace_default_permissions(payload.role), **__import__('json').loads(member.access_overrides or '{}').get('permissions', {})}
            assert_within_ceiling(await get_workspace_permissions(ctx['user'].id, workspace_id) or {}, candidate)
        member.role = payload.role
        await session.commit()
        username = (await session.get(User, user_id)).username
    return JSONResponse(_member_to_dict(member, username))


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(workspace_id: int, user_id: int, ctx=Depends(require_workspace_management("workspace_members"))):
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
        target = await session.get(User, user_id)
        if target is not None and target.is_root and not is_root_user(ctx["user"]):
            return JSONResponse({"error": "Нельзя удалять root-пользователя из окружения"}, status_code=403)
        if member.role == WS_ROLE_OWNER and not actor_is_super:
            err = await _can_leave_ownership(session, ctx["workspace"].id, ctx["user"].id, user_id)
        else:
            err = _can_manage(ctx["role"], actor_is_super, member.role)
        if err:
            return JSONResponse({"error": err}, status_code=403)
        await session.delete(member)
        # tombstone: автодобавление при рестарте не должно возвращать удалённых
        existing_mark = (await session.execute(
            select(WorkspaceRemoval).where(
                WorkspaceRemoval.workspace_id == ctx["workspace"].id,
                WorkspaceRemoval.user_id == user_id,
            )
        )).scalar_one_or_none()
        if existing_mark is None:
            session.add(WorkspaceRemoval(workspace_id=ctx["workspace"].id, user_id=user_id))
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
