import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.web.api.access_validation import read_object
from app.core.database import async_session
from app.core.models import Role, UserRole
from app.web.api.access_validation import validate_name, validate_permissions
from app.core.permissions import (
    assert_features_grantable,
    assert_within_ceiling,
    get_user_permissions,
    require_permission,
    require_any_permission,
    require_root,
)

router = APIRouter(prefix="/api/roles", tags=["roles"])


def _role_permissions(role) -> dict:
    if isinstance(role.permissions, str):
        try:
            return json.loads(role.permissions or '{}')
        except ValueError:
            return {}
    return dict(role.permissions or {})


@router.get('')
async def list_roles(deleted: bool = False, user=Depends(require_any_permission('users', 'users_manage'))):
    if deleted and not user.is_root:
        raise HTTPException(403, 'Корзина профилей приложения доступна только суперадмину')
    async with async_session() as session:
        r = await session.execute(select(Role).where(Role.deleted_at.is_not(None) if deleted else Role.deleted_at.is_(None)).order_by(Role.id))
        roles = r.scalars().all()
    return JSONResponse([{
        'id': role.id,
        'name': role.name,
        'deleted_at': role.deleted_at.isoformat() if role.deleted_at else None,
        'permissions': json.loads(role.permissions) if isinstance(role.permissions, str) else role.permissions,
    } for role in roles])


@router.post('')
async def create_role(request: Request, user=Depends(require_root())):
    data = await read_object(request)
    name = validate_name(data.get('name'))
    if name == 'superadmin':
        raise HTTPException(status_code=403, detail='Системную роль суперадмина нельзя создавать')
    permissions = validate_permissions(data.get('permissions', {}))
    granter = await get_user_permissions(user.id)
    assert_within_ceiling(granter, permissions)
    await assert_features_grantable(permissions)
    async with async_session() as session:
        existing = await session.execute(select(Role).where(Role.name == name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail='Название уже занято. Удалённый профиль можно восстановить.')
        role = Role(name=name, permissions=json.dumps(permissions, ensure_ascii=False))
        session.add(role)
        await session.commit()
        await session.refresh(role)
    return JSONResponse({'id': role.id, 'name': role.name, 'permissions': permissions}, status_code=201)


@router.put('/{role_id}')
async def update_role(role_id: int, request: Request, user=Depends(require_root())):
    data = await read_object(request)
    granter = await get_user_permissions(user.id)
    async with async_session() as session:
        role = await session.get(Role, role_id)
        if not role or role.deleted_at:
            raise HTTPException(status_code=404, detail='Role not found')
        if role.name == 'superadmin':
            raise HTTPException(status_code=403, detail='Cannot modify superadmin role')
        if 'name' in data:
            next_name = validate_name(data['name'])
            if next_name == 'superadmin' and role.name != 'superadmin':
                raise HTTPException(status_code=403, detail='Нельзя создать или переименовать роль в superadmin')
            clash = (await session.execute(select(Role).where(Role.name == next_name, Role.id != role_id))).scalar_one_or_none()
            if clash:
                raise HTTPException(status_code=400, detail='Роль с таким названием уже есть')
            role.name = next_name
        if 'permissions' in data:
            permissions = validate_permissions(data['permissions'])
            assert_within_ceiling(granter, permissions)
            previous = _role_permissions(role)
            await assert_features_grantable({key: True for key, value in permissions.items() if value and not previous.get(key)})
            role.permissions = json.dumps(permissions, ensure_ascii=False)
        await session.commit()
    return JSONResponse({'ok': True})


@router.delete('/{role_id}')
async def delete_role(role_id: int, user=Depends(require_root())):
    async with async_session() as session:
        role = await session.get(Role, role_id)
        if not role or role.deleted_at:
            raise HTTPException(status_code=404, detail='Role not found')
        if role.name == 'superadmin':
            raise HTTPException(status_code=403, detail='Cannot delete superadmin role')
        # удалять можно только роль, чьи права сам способен выдать
        assert_within_ceiling(await get_user_permissions(user.id), _role_permissions(role),
                              detail='Нельзя удалить роль с правами выше ваших')
        await session.execute(UserRole.__table__.delete().where(UserRole.role_id == role_id))
        role.deleted_at = datetime.now(timezone.utc)
        await session.commit()
    return JSONResponse({'ok': True})


@router.post('/{role_id}/restore')
async def restore_role(role_id: int, user=Depends(require_root())):
    async with async_session() as session:
        role = await session.get(Role, role_id)
        if not role or not role.deleted_at:
            raise HTTPException(404, 'Удалённая роль не найдена')
        if role.name == 'superadmin':
            raise HTTPException(403, 'Системная роль защищена')
        # Restoration recovers the profile, never its former assignments.
        await session.execute(UserRole.__table__.delete().where(UserRole.role_id == role_id))
        role.deleted_at = None
        await session.commit()
    return {'ok': True}
