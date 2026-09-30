import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, update

from app.core.auth import hash_password
from app.core.database import async_session
from app.core.models import Role, User, UserGroup, UserRole, WorkspaceMember
from app.core.models import (
    ActivityLog, ClientResponsible, GeneratedReport, Module, Note, NoteFolder,
    Notification, SavedView, Sprint, Task, TaskCoExecutor, TaskComment,
    UserClientAccess, Workspace, WorkspaceKnowledge,
)
from app.core.permissions import (
    assert_features_grantable,
    assert_within_ceiling,
    get_current_user,
    get_user_permissions,
    get_user_role_names,
    get_workspace_role,
    require_permission,
    require_role,
    resolve_workspace,
    user_is_superadmin,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get('')
async def list_users(user=Depends(get_current_user)):
    async with async_session() as session:
        r = await session.execute(select(User).order_by(User.id))
        users = r.scalars().all()
        all_links = (await session.execute(select(UserGroup))).scalars().all()
        groups_by_user: dict[int, list[int]] = {}
        for link in all_links:
            groups_by_user.setdefault(link.user_id, []).append(link.group_id)
        result = []
        for u in users:
            rr = await session.execute(select(UserRole).where(UserRole.user_id == u.id))
            roles = rr.scalars().all()
            result.append({
                'id': u.id,
                'username': u.username,
                'created_at': u.created_at.isoformat() if u.created_at else '',
                'roles': [{'id': ur.role_id, 'name': (await session.get(Role, ur.role_id)).name} for ur in roles if await session.get(Role, ur.role_id)],
                'group_ids': groups_by_user.get(u.id, []),
            })
    return JSONResponse(result)


@router.post('')
async def create_user(request: Request, user=Depends(get_current_user)):
    data = await request.json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail='Логин должен быть минимум 2 символа')
    if not password or len(password) < 4:
        raise HTTPException(status_code=400, detail='Пароль минимум 4 символа')
    workspace_id = data.get('workspace_id')
    ws_role = (data.get('role') or 'member').strip()
    if ws_role not in ('admin', 'member'):
        raise HTTPException(status_code=400, detail='Роль: admin или member')
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        actor_is_super = user_is_superadmin(role_names)
        target_ws = None
        if workspace_id is not None:
            target_ws, actor_ws_role = await resolve_workspace(session, user, role_names, int(workspace_id))
            if not actor_is_super and actor_ws_role not in ('owner', 'admin'):
                raise HTTPException(status_code=403, detail='Forbidden')
        elif not actor_is_super:
            raise HTTPException(status_code=403, detail='Forbidden')
        existing = await session.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail='Пользователь уже существует')
        u = User(username=username, password_hash=hash_password(password))
        session.add(u)
        await session.flush()
        if target_ws is not None:
            session.add(WorkspaceMember(workspace_id=target_ws.id, user_id=u.id, role=ws_role))
        await session.commit()
        await session.refresh(u)
    return JSONResponse({'id': u.id, 'username': u.username}, status_code=201)


@router.put('/{user_id}/password')
async def set_password(user_id: int, request: Request, user=Depends(get_current_user)):
    data = await request.json()
    password = data.get('password') or ''
    if len(password) < 4:
        raise HTTPException(status_code=400, detail='Пароль минимум 4 символа')
    async with async_session() as session:
        target = await session.get(User, user_id)
        if not target:
            raise HTTPException(status_code=404, detail='User not found')
        target_roles = (await session.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )).scalars().all()
        for ur_ in target_roles:
            r = await session.get(Role, ur_.role_id)
            if r and r.name == 'superadmin':
                # пароль суперадмина через этот эндпоинт не меняется вообще:
                # ни чужими, ни им самим. Своя смена — только через
                # POST /api/users/change-password с проверкой текущего пароля.
                raise HTTPException(status_code=403, detail='Cannot change the superadmin password')
        actor_permissions = await get_user_permissions(user.id)
        if user.id == user_id:
            # свой пароль — запрет только при явном False (снятая галочка).
            # Отсутствие ключа = разрешено: не ломаем legacy-роли и юзеров
            # вообще без ролей; миграция всем ставит True.
            if not (actor_permissions.get('all') or actor_permissions.get('users_password_own', True) is not False):
                raise HTTPException(status_code=403, detail='Нет права "users_password_own"')
        elif not await _can_reset_password(session, user, actor_permissions, user_id):
            raise HTTPException(status_code=403, detail='Forbidden')
        target.password_hash = hash_password(password)
        await session.commit()
    return JSONResponse({'ok': True})


async def _can_reset_password(session, actor, actor_permissions: dict, target_id: int) -> bool:
    """Может ли actor сбросить чужой пароль (не суперадмина — проверено выше).

    - суперадмин (`all`) — всегда;
    - иначе: общее окружение, где у actor есть право users_password_reset
      (кастомная роль окружения или роль приложения), и базовый rank actor
      строго выше rank цели (owner → admin → member). Ровесникам и старшим —
      нельзя, вне общих окружений — нельзя.
    """
    if actor_permissions.get('all'):
        return True
    from app.core.models import WorkspaceMember
    from app.core.permissions import get_workspace_permissions, workspace_role_rank
    memberships = (await session.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == actor.id)
    )).scalars().all()
    for membership in memberships:
        target_role = await get_workspace_role(session, target_id, membership.workspace_id)
        if target_role is None:
            continue
        if workspace_role_rank(membership.role) <= workspace_role_rank(target_role):
            continue
        ws_permissions = await get_workspace_permissions(actor.id, membership.workspace_id) or {}
        if ws_permissions.get('users_password_reset') or actor_permissions.get('users_password_reset'):
            return True
    return False


@router.put('/{user_id}/role')
async def set_role(user_id: int, request: Request, user=Depends(require_permission('users'))):
    data = await request.json()
    role_id = data.get('role_id')
    async with async_session() as session:
        u = await session.get(User, user_id)
        if not u:
            raise HTTPException(status_code=404, detail='User not found')
        ur_check = await session.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        target_roles = ur_check.scalars().all()
        target_is_superadmin = False
        for ur_ in target_roles:
            r = await session.get(Role, ur_.role_id)
            if r and r.name == 'superadmin':
                target_is_superadmin = True
        r = await session.get(Role, role_id)
        if not r:
            raise HTTPException(status_code=404, detail='Role not found')
        if r.name == 'superadmin':
            raise HTTPException(status_code=403, detail='Superadmin cannot be assigned here')
        if target_is_superadmin:
            raise HTTPException(status_code=403, detail='Cannot change the superadmin role')
        # потолок: назначаемая роль не должна давать прав сверх прав назначающего
        role_permissions = (
            json.loads(r.permissions) if isinstance(r.permissions, str) else (r.permissions or {})
        )
        assert_within_ceiling(await get_user_permissions(user.id), role_permissions,
                              detail='Назначаемая роль даёт права выше ваших')
        await assert_features_grantable(role_permissions)
        await session.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))
        existing = await session.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        )
        if not existing.scalar_one_or_none():
            session.add(UserRole(user_id=user_id, role_id=role_id))
            await session.commit()
    return JSONResponse({'ok': True})


@router.delete('/{user_id}')
async def delete_user(user_id: int, user=Depends(require_role(['superadmin']))):
    async with async_session() as session:
        u = await session.get(User, user_id)
        if not u:
            raise HTTPException(status_code=404, detail='User not found')
        ur_check = await session.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        for ur_ in ur_check.scalars().all():
            r = await session.get(Role, ur_.role_id)
            if r and r.name == 'superadmin':
                raise HTTPException(status_code=403, detail='Cannot delete the superadmin user')
        await session.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))
        # Preserve shared work and history, detaching the deleted account.
        # Tasks/comments have older foreign keys without ON DELETE SET NULL.
        for model, field in (
            (Task, 'creator_id'), (Task, 'assignee_id'), (Task, 'co_executor_id'),
            (TaskComment, 'user_id'), (ActivityLog, 'user_id'),
            (GeneratedReport, 'created_by'), (Module, 'assignee_id'),
            (Workspace, 'created_by'), (Sprint, 'created_by'),
            (WorkspaceKnowledge, 'created_by'),
        ):
            await session.execute(update(model).where(getattr(model, field) == user_id).values({field: None}))
        # Delete account-owned records explicitly, including on SQLite where
        # foreign-key cascades may be disabled. Bypass ORM backref nullification.
        for model in (
            WorkspaceMember, UserGroup, UserClientAccess, ClientResponsible,
            TaskCoExecutor, Notification, SavedView, Note, NoteFolder,
        ):
            await session.execute(delete(model).where(model.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()
    return JSONResponse({'ok': True})
