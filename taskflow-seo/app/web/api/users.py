from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.auth import hash_password
from app.core.database import async_session
from app.core.models import Role, User, UserRole, WorkspaceMember
from app.core.permissions import (
    get_current_user,
    get_user_role_names,
    get_workspace_role,
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
        result = []
        for u in users:
            rr = await session.execute(select(UserRole).where(UserRole.user_id == u.id))
            roles = rr.scalars().all()
            result.append({
                'id': u.id,
                'username': u.username,
                'created_at': u.created_at.isoformat() if u.created_at else '',
                'roles': [{'id': ur.role_id, 'name': (await session.get(Role, ur.role_id)).name} for ur in roles if await session.get(Role, ur.role_id)],
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
        if user.id == user_id:
            pass  # свой пароль менять можно всегда
        else:
            role_names = await get_user_role_names(user.id)
            if user_is_superadmin(role_names):
                pass
            else:
                # админ воркспейса — только участникам своих воркспейсов, но не владельцу
                allowed = False
                memberships = (await session.execute(
                    select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
                )).scalars().all()
                for membership in memberships:
                    if membership.role not in ('owner', 'admin'):
                        continue
                    target_role = await get_workspace_role(session, user_id, membership.workspace_id)
                    if target_role is None:
                        continue
                    if target_role == 'owner':
                        continue
                    allowed = True
                    break
                if not allowed:
                    raise HTTPException(status_code=403, detail='Forbidden')
        target.password_hash = hash_password(password)
        await session.commit()
    return JSONResponse({'ok': True})


@router.put('/{user_id}/role')
async def set_role(user_id: int, request: Request, user=Depends(require_role(['superadmin']))):
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
        superadmin_role = await session.execute(select(Role).where(Role.name == 'superadmin'))
        superadmin_role = superadmin_role.scalar_one_or_none()
        superadmin_count = 0
        if superadmin_role:
            superadmin_count = len((await session.execute(
                select(UserRole).where(UserRole.role_id == superadmin_role.id)
            )).scalars().all())
        if target_is_superadmin and r.name != 'superadmin' and superadmin_count <= 1:
            raise HTTPException(status_code=403, detail='Cannot remove the last superadmin')
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
        superadmin_role = await session.execute(select(Role).where(Role.name == 'superadmin'))
        superadmin_role = superadmin_role.scalar_one_or_none()
        superadmin_count = 0
        if superadmin_role:
            superadmin_count = len((await session.execute(
                select(UserRole).where(UserRole.role_id == superadmin_role.id)
            )).scalars().all())
        for ur_ in ur_check.scalars().all():
            r = await session.get(Role, ur_.role_id)
            if r and r.name == 'superadmin' and superadmin_count <= 1:
                raise HTTPException(status_code=403, detail='Cannot delete the last superadmin user')
        await session.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))
        await session.delete(u)
        await session.commit()
    return JSONResponse({'ok': True})
