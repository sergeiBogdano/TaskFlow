import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import Group, User, UserGroup
from app.core.permissions import assert_within_ceiling, get_user_permissions, require_role

router = APIRouter(prefix="/api/groups", tags=["groups"])

# группы назначает/редактирует только суперадмин (модель: «Группы» глобальные,
# создаёт/назначает только суперадмин); потолок действует и для него-самого
# через assert_within_ceiling только для не-суперадминов — здесь всегда superadmin.


def _group_payload(group: Group, member_ids: list[int] | None = None) -> dict:
    perms = group.permissions
    if isinstance(perms, str):
        try:
            perms = json.loads(perms or '{}')
        except ValueError:
            perms = {}
    payload = {'id': group.id, 'name': group.name, 'permissions': perms or {}}
    if member_ids is not None:
        payload['user_ids'] = member_ids
    return payload


@router.get('')
async def list_groups(user=Depends(require_role(['superadmin']))):
    async with async_session() as session:
        groups = (await session.execute(select(Group).order_by(Group.id))).scalars().all()
        links = (await session.execute(select(UserGroup))).scalars().all()
    members: dict[int, list[int]] = {}
    for link in links:
        members.setdefault(link.group_id, []).append(link.user_id)
    return JSONResponse([
        _group_payload(group, members.get(group.id, [])) for group in groups
    ])


@router.post('')
async def create_group(request: Request, user=Depends(require_role(['superadmin']))):
    data = await request.json()
    name = (data.get('name') or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='Название группы обязательно')
    permissions = data.get('permissions') or {}
    # даже суперадмин создаёт группу с правами из каталога — потолок не нужен (all)
    assert_within_ceiling(await get_user_permissions(user.id), permissions)
    async with async_session() as session:
        existing = await session.execute(select(Group).where(Group.name == name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail='Группа уже существует')
        group = Group(name=name, permissions=json.dumps(permissions, ensure_ascii=False))
        session.add(group)
        await session.commit()
        await session.refresh(group)
    return JSONResponse(_group_payload(group, []), status_code=201)


@router.put('/{group_id}')
async def update_group(group_id: int, request: Request, user=Depends(require_role(['superadmin']))):
    data = await request.json()
    async with async_session() as session:
        group = await session.get(Group, group_id)
        if not group:
            raise HTTPException(status_code=404, detail='Group not found')
        if data.get('name'):
            group.name = data['name'].strip()
        if 'permissions' in data:
            permissions = data.get('permissions') or {}
            assert_within_ceiling(await get_user_permissions(user.id), permissions)
            group.permissions = json.dumps(permissions, ensure_ascii=False)
        await session.commit()
    return JSONResponse({'ok': True})


@router.delete('/{group_id}')
async def delete_group(group_id: int, user=Depends(require_role(['superadmin']))):
    async with async_session() as session:
        group = await session.get(Group, group_id)
        if not group:
            raise HTTPException(status_code=404, detail='Group not found')
        await session.execute(UserGroup.__table__.delete().where(UserGroup.group_id == group_id))
        await session.delete(group)
        await session.commit()
    return JSONResponse({'ok': True})


@router.put('/{group_id}/members')
async def set_group_members(group_id: int, request: Request, user=Depends(require_role(['superadmin']))):
    data = await request.json()
    user_ids = data.get('user_ids')
    if not isinstance(user_ids, list):
        raise HTTPException(status_code=400, detail='user_ids: список')
    async with async_session() as session:
        group = await session.get(Group, group_id)
        if not group:
            raise HTTPException(status_code=404, detail='Group not found')
        existing_users = {
            row[0] for row in (await session.execute(
                select(User.id).where(User.id.in_([int(i) for i in user_ids] or [0]))
            )).all()
        }
        await session.execute(UserGroup.__table__.delete().where(UserGroup.group_id == group_id))
        for raw in user_ids:
            uid = int(raw)
            if uid in existing_users:
                session.add(UserGroup(group_id=group_id, user_id=uid))
        await session.commit()
    return JSONResponse({'ok': True})
