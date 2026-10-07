import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import Role, UserRole
from app.core.permissions import (
    assert_features_grantable,
    assert_within_ceiling,
    get_user_permissions,
    require_permission,
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
async def list_roles(user=Depends(require_permission('users'))):
    async with async_session() as session:
        r = await session.execute(select(Role).order_by(Role.id))
        roles = r.scalars().all()
    return JSONResponse([{
        'id': role.id,
        'name': role.name,
        'permissions': json.loads(role.permissions) if isinstance(role.permissions, str) else role.permissions,
    } for role in roles])


@router.post('')
async def create_role(request: Request, user=Depends(require_root())):
    data = await request.json()
    name = (data.get('name') or '').strip()
    permissions = data.get('permissions') or {}
    granter = await get_user_permissions(user.id)
    assert_within_ceiling(granter, permissions)
    await assert_features_grantable(permissions)
    async with async_session() as session:
        existing = await session.execute(select(Role).where(Role.name == name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail='Role already exists')
        role = Role(name=name, permissions=json.dumps(permissions, ensure_ascii=False))
        session.add(role)
        await session.commit()
        await session.refresh(role)
    return JSONResponse({'id': role.id, 'name': role.name, 'permissions': permissions}, status_code=201)


@router.put('/{role_id}')
async def update_role(role_id: int, request: Request, user=Depends(require_root())):
    data = await request.json()
    granter = await get_user_permissions(user.id)
    async with async_session() as session:
        role = await session.get(Role, role_id)
        if not role:
            raise HTTPException(status_code=404, detail='Role not found')
        if role.name == 'superadmin':
            raise HTTPException(status_code=403, detail='Cannot modify superadmin role')
        if data.get('name'):
            next_name = data['name'].strip()
            if next_name == 'superadmin' and role.name != 'superadmin':
                raise HTTPException(status_code=403, detail='Нельзя создать или переименовать роль в superadmin')
            role.name = next_name
        if 'permissions' in data:
            assert_within_ceiling(granter, data.get('permissions') or {})
            await assert_features_grantable(data.get('permissions') or {})
            role.permissions = json.dumps(data.get('permissions') or {}, ensure_ascii=False)
        await session.commit()
    return JSONResponse({'ok': True})


@router.delete('/{role_id}')
async def delete_role(role_id: int, user=Depends(require_root())):
    async with async_session() as session:
        role = await session.get(Role, role_id)
        if not role:
            raise HTTPException(status_code=404, detail='Role not found')
        if role.name == 'superadmin':
            raise HTTPException(status_code=403, detail='Cannot delete superadmin role')
        # удалять можно только роль, чьи права сам способен выдать
        assert_within_ceiling(await get_user_permissions(user.id), _role_permissions(role),
                              detail='Нельзя удалить роль с правами выше ваших')
        await session.execute(UserRole.__table__.delete().where(UserRole.role_id == role_id))
        await session.delete(role)
        await session.commit()
    return JSONResponse({'ok': True})
