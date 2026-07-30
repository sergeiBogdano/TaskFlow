import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import Role, UserRole
from app.core.permissions import require_role

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get('')
async def list_roles(user=Depends(require_role(['superadmin']))):
    async with async_session() as session:
        r = await session.execute(select(Role).order_by(Role.id))
        roles = r.scalars().all()
    return JSONResponse([{
        'id': role.id,
        'name': role.name,
        'permissions': json.loads(role.permissions) if isinstance(role.permissions, str) else role.permissions,
    } for role in roles])


@router.post('')
async def create_role(request: Request, user=Depends(require_role(['superadmin']))):
    data = await request.json()
    name = (data.get('name') or '').strip()
    permissions = data.get('permissions') or {}
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
async def update_role(role_id: int, request: Request, user=Depends(require_role(['superadmin']))):
    data = await request.json()
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
            role.permissions = json.dumps(data.get('permissions') or {}, ensure_ascii=False)
        await session.commit()
    return JSONResponse({'ok': True})


@router.delete('/{role_id}')
async def delete_role(role_id: int, user=Depends(require_role(['superadmin']))):
    async with async_session() as session:
        role = await session.get(Role, role_id)
        if not role:
            raise HTTPException(status_code=404, detail='Role not found')
        if role.name == 'superadmin':
            raise HTTPException(status_code=403, detail='Cannot delete superadmin role')
        await session.execute(UserRole.__table__.delete().where(UserRole.role_id == role_id))
        await session.delete(role)
        await session.commit()
    return JSONResponse({'ok': True})
