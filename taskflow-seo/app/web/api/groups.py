import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.web.api.access_validation import read_object
from app.core.database import async_session
from app.core.models import Group, User, UserGroup
from app.web.api.access_validation import validate_name, validate_permissions
from app.core.permissions import (
    assert_features_grantable,
    assert_within_ceiling,
    get_user_permissions,
    require_role,
)

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
    data = await read_object(request)
    name = validate_name(data.get('name'), 'Название группы')
    permissions = validate_permissions(data.get('permissions', {}))
    # даже суперадмин создаёт группу с правами из каталога — потолок не нужен (all)
    assert_within_ceiling(await get_user_permissions(user.id), permissions)
    await assert_features_grantable(permissions)
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
    data = await read_object(request)
    async with async_session() as session:
        group = await session.get(Group, group_id)
        if not group:
            raise HTTPException(status_code=404, detail='Group not found')
        if 'name' in data:
            name = validate_name(data['name'], 'Название группы')
            clash = (await session.execute(select(Group).where(Group.name == name, Group.id != group_id))).scalar_one_or_none()
            if clash:
                raise HTTPException(status_code=400, detail='Группа с таким названием уже есть')
            group.name = name
        if 'permissions' in data:
            permissions = validate_permissions(data['permissions'])
            assert_within_ceiling(await get_user_permissions(user.id), permissions)
            previous = _group_payload(group)['permissions']
            await assert_features_grantable({key: True for key, value in permissions.items() if value and not previous.get(key)})
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
        from app.core.models import FeatureOverride
        await session.execute(FeatureOverride.__table__.delete().where(FeatureOverride.scope == 'group', FeatureOverride.target_id == group_id))
        await session.delete(group)
        await session.commit()
    return JSONResponse({'ok': True})


@router.put('/{group_id}/members')
async def set_group_members(group_id: int, request: Request, user=Depends(require_role(['superadmin']))):
    data = await read_object(request)
    user_ids = data.get('user_ids')
    if not isinstance(user_ids, list):
        raise HTTPException(status_code=400, detail='user_ids: список')
    async with async_session() as session:
        group = await session.get(Group, group_id)
        if not group:
            raise HTTPException(status_code=404, detail='Group not found')
        try:
            wanted_ids = list(dict.fromkeys(int(item) for item in user_ids))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail='user_ids: только числа')
        existing_users = {
            row[0] for row in (await session.execute(
                select(User.id).where(User.id.in_(wanted_ids or [0]))
            )).all()
        }
        await session.execute(UserGroup.__table__.delete().where(UserGroup.group_id == group_id))
        for uid in wanted_ids:
            if uid in existing_users:
                session.add(UserGroup(group_id=group_id, user_id=uid))
        await session.commit()
    return JSONResponse({'ok': True})
