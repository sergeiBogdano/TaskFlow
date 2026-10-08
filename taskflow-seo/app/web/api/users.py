from app.core.config import settings
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, update

from app.core.auth import hash_password
from app.core.database import async_session
from app.core.models import Role, User, UserGroup, UserRole, WorkspaceMember
from app.core.models import (
    ActivityLog, ClientResponsible, GeneratedReport, Module, Note, NoteFolder, CrmDeal, CrmActivity,
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
    require_root,
    resolve_workspace,
    is_root_user,
    is_feature_available,
    workspace_id_from_request,
    user_is_superadmin,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get('')
async def list_users(request: Request, user=Depends(get_current_user)):
    async with async_session() as session:
        app_permissions = await get_user_permissions(user.id)
        can_manage_accounts = is_root_user(user) or (
            app_permissions.get('users_manage') and await is_feature_available(user, 'users_manage')
        )
        if can_manage_accounts and (workspace_id_from_request(request) is None or request.query_params.get('scope') == 'platform'):
            user_query = select(User)
        else:
            roles = await get_user_role_names(user.id)
            try:
                workspace, _ = await resolve_workspace(
                    session, user, roles, workspace_id_from_request(request)
                )
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                # A newly created account may not have been invited yet.
                # It can see itself, but never a global account directory.
                user_query = select(User).where(User.id == user.id)
            else:
                user_query = select(User).join(
                    WorkspaceMember, WorkspaceMember.user_id == User.id
                ).where(WorkspaceMember.workspace_id == workspace.id)
        r = await session.execute(user_query.order_by(User.id))
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
                'is_root': bool(u.is_root),
                'is_active': bool(u.is_active),
                'must_change_password': bool(u.must_change_password),
                'created_at': u.created_at.isoformat() if u.created_at else '',
                'roles': [{'id': ur.role_id, 'name': (await session.get(Role, ur.role_id)).name} for ur in roles if await session.get(Role, ur.role_id)],
                'group_ids': groups_by_user.get(u.id, []),
            })
    return JSONResponse(result)


@router.post('')
async def create_user(request: Request, user=Depends(require_permission('users_manage'))):
    data = await request.json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail='Логин должен быть минимум 2 символа')
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail='Пароль минимум 8 символов')
    workspace_id = data.get('workspace_id')
    ws_role = (data.get('role') or 'member').strip()
    if ws_role not in ('admin', 'member'):
        raise HTTPException(status_code=400, detail='Роль: admin или member')
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        actor_is_super = is_root_user(user)
        actor_permissions = await get_user_permissions(user.id)
        if not actor_is_super and not actor_permissions.get('users_manage'):
            raise HTTPException(status_code=403, detail='Создавать аккаунты может администратор приложения')
        target_ws = None
        if workspace_id is not None:
            target_ws, actor_ws_role = await resolve_workspace(session, user, role_names, int(workspace_id))
            if not actor_is_super and actor_ws_role not in ('owner', 'admin'):
                raise HTTPException(status_code=403, detail='Forbidden')
            if not actor_is_super and actor_ws_role == 'admin' and ws_role != 'member':
                raise HTTPException(
                    status_code=403,
                    detail='Администратор окружения может создавать только участников',
                )
        elif not actor_is_super and not actor_permissions.get('users_manage'):
            raise HTTPException(status_code=403, detail='Forbidden')
        existing = await session.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail='Пользователь уже существует')
        u = User(username=username, password_hash=hash_password(password),
                 must_change_password=bool(data.get('must_change_password', True)))
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
    if len(password) < 8:
        raise HTTPException(status_code=400, detail='Пароль минимум 8 символов')
    async with async_session() as session:
        target = await session.get(User, user_id)
        if not target:
            raise HTTPException(status_code=404, detail='User not found')
        if target.is_root:
            raise HTTPException(status_code=403, detail='Нельзя менять пароль root через административный API')
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
            raise HTTPException(status_code=403, detail='Свой пароль меняйте с подтверждением текущего пароля')
        if not await _can_reset_password(session, user, actor_permissions, user_id):
            raise HTTPException(status_code=403, detail='Forbidden')
        target.password_hash = hash_password(password)
        target.session_version += 1
        target.must_change_password = user.id != user_id
        await session.commit()
    return JSONResponse({'ok': True})


async def _can_reset_password(session, actor, actor_permissions: dict, target_id: int) -> bool:
    """Root resets ordinary accounts; account administrators require both global
    account-management and password-reset capabilities. Space membership alone
    never permits taking over a platform account.
    """
    if actor_permissions.get('all'):
        return True
    from app.core.permissions import is_feature_available
    if actor_permissions.get('users_manage') and actor_permissions.get('users_password_reset') and await is_feature_available(actor, 'users_manage') and await is_feature_available(actor, 'users_password_reset'):
        target_permissions = await get_user_permissions(target_id)
        return not (target_permissions.get('all') or target_permissions.get('users_manage') or target_permissions.get('users'))
    # Space administrators cannot take over platform accounts by inviting them.
    return False


@router.put('/{user_id}/role')
async def set_role(user_id: int, request: Request, user=Depends(require_permission('users_manage'))):
    data = await request.json()
    role_id = data.get('role_id')
    async with async_session() as session:
        u = await session.get(User, user_id)
        if not u:
            raise HTTPException(status_code=404, detail='User not found')
        if u.is_root:
            raise HTTPException(status_code=403, detail='Нельзя менять роль root-пользователя')
        if not user.is_root:
            target_permissions = await get_user_permissions(user_id)
            if user_id == user.id or any(target_permissions.get(key) for key in ('users', 'users_manage', 'all')):
                raise HTTPException(403, 'Нельзя изменять себя или администратора приложения')
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
        if not r or r.deleted_at:
            raise HTTPException(status_code=404, detail='Role not found')
        if r.name == 'superadmin':
            raise HTTPException(status_code=403, detail='Superadmin cannot be assigned here')
        if target_is_superadmin:
            raise HTTPException(status_code=403, detail='Cannot change the superadmin role')
        # потолок: назначаемая роль не должна давать прав сверх прав назначающего
        role_permissions = (
            json.loads(r.permissions) if isinstance(r.permissions, str) else (r.permissions or {})
        )
        if not user.is_root and any(role_permissions.get(key) for key in ('users', 'users_manage', 'settings')):
            raise HTTPException(403, 'Профили администраторов приложения назначает только root')
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
        if u.is_root:
            raise HTTPException(status_code=403, detail='Нельзя удалить root-пользователя')
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
            (CrmDeal, 'assignee_id'), (CrmActivity, 'created_by'),
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
        from app.core.models import UserSettings, WorkspaceRemoval, FeatureOverride
        await session.execute(delete(WorkspaceRemoval).where(WorkspaceRemoval.user_id == user_id))
        await session.execute(delete(FeatureOverride).where(FeatureOverride.scope == 'user', FeatureOverride.target_id == user_id))
        await session.execute(delete(UserSettings).where(UserSettings.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()
    return JSONResponse({'ok': True})


@router.post('/change-password')
async def change_password(request: Request, user=Depends(get_current_user)):
    from app.core.auth import COOKIE_NAME, make_session_token, verify_password
    if user.is_root:
        raise HTTPException(status_code=403, detail='Пароль суперадмина меняется только командой на сервере')
    permissions = await get_user_permissions(user.id)
    from app.core.permissions import is_feature_available
    if not user.must_change_password and not (permissions.get('users_password_own', True) and await is_feature_available(user, 'users_password_own')):
        raise HTTPException(status_code=403, detail='Нет права смены своего пароля')
    data = await request.json() if 'application/json' in request.headers.get('content-type', '') else await request.form()
    if not verify_password(data.get('current_password', ''), user.password_hash):
        raise HTTPException(status_code=400, detail='Неверный текущий пароль')
    password = data.get('new_password', '')
    if len(password) < 8:
        raise HTTPException(status_code=400, detail='Новый пароль должен содержать минимум 8 символов')
    async with async_session() as session:
        account = await session.get(User, user.id)
        account.password_hash = hash_password(password)
        account.must_change_password = False
        account.session_version += 1
        await session.commit()
        response = JSONResponse({'ok': True})
        response.set_cookie(COOKIE_NAME, make_session_token(account.id, account.session_version),
                            httponly=True, samesite='lax', max_age=86400 * 30)
        return response


@router.patch('/{user_id}/status')
async def set_user_status(user_id: int, request: Request, actor=Depends(require_permission('users_manage'))):
    data = await request.json()
    if not isinstance(data.get('is_active'), bool):
        raise HTTPException(status_code=400, detail='is_active должен быть логическим значением')
    async with async_session() as session:
        account = await session.get(User, user_id)
        if not account:
            raise HTTPException(status_code=404, detail='Пользователь не найден')
        if account.is_root or account.id == actor.id:
            raise HTTPException(status_code=403, detail='Нельзя блокировать root или самого себя')
        target_permissions = await get_user_permissions(account.id)
        if not actor.is_root and (target_permissions.get('users_manage') or target_permissions.get('users')):
            raise HTTPException(status_code=403, detail='Управлять администраторами может только суперадмин')
        account.is_active = data['is_active']
        account.session_version += 1
        await session.commit()
    return {'ok': True}


@router.get('/{user_id}/access')
async def explain_access(user_id: int, actor=Depends(require_permission('users_manage'))):
    from app.core.permissions import get_workspace_permissions, get_effective_features
    async with async_session() as session:
        account = await session.get(User, user_id)
        if not account:
            raise HTTPException(status_code=404, detail='Пользователь не найден')
        rows = (await session.execute(select(WorkspaceMember, Workspace.name).join(
            Workspace, Workspace.id == WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user_id))).all()
    spaces = []
    for member, name in rows:
        spaces.append({'id': member.workspace_id, 'name': name, 'rank': member.role,
                       'custom_role_id': member.custom_role_id,
                       'permissions': await get_workspace_permissions(user_id, member.workspace_id),
                       'features': await get_effective_features(account, member.workspace_id)})
    from app.core.permission_catalog import work_scope_keys
    app_permissions = {key: value for key, value in (await get_user_permissions(user_id)).items() if key not in set(work_scope_keys())}
    return {'app_permissions': app_permissions, 'spaces': spaces}
