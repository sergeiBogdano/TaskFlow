"""Кастомные роли окружения (Ф7): CRUD + назначение участнику.

Только scope=work-ключи, кран доступности (Ф6) и потолок (Ф3/Ф4).
Базовые rank owner/admin/member управляют членством, кастомная роль задаёт точный набор рабочих прав.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.web.api.access_validation import read_object
from app.core.database import async_session
from app.core.models import User, WorkspaceMember, WorkspaceRole
from app.core.permission_catalog import work_scope_keys
from app.core.permissions import (
    assert_within_ceiling,
    get_effective_features,
    get_user_permissions,
    require_workspace_role,
    require_workspace_management,
    is_root_user,
    workspace_role_rank,
)

from app.core.access_policy import parse_policy, validate_fields, assert_field_ceiling

router = APIRouter(prefix="/api/workspaces", tags=["workspace-roles"])

_WORK_KEYS = set(work_scope_keys())


def _role_permissions(role: WorkspaceRole) -> dict:
    if isinstance(role.permissions, str):
        try:
            return json.loads(role.permissions or "{}")
        except ValueError:
            return {}
    return dict(role.permissions or {})


def _role_to_dict(role: WorkspaceRole) -> dict:
    return {
        "id": role.id,
        "workspace_id": role.workspace_id,
        "name": role.name,
        "permissions": _role_permissions(role),
        "field_access": parse_policy(role.field_access),
        "created_at": role.created_at.isoformat() if role.created_at else None,
    }


def _validate_payload(data: dict) -> tuple[str, dict]:
    from app.web.api.access_validation import validate_name
    name = validate_name(data.get('name'), 'Название роли')
    raw = data.get("permissions", {})
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="permissions должен быть объектом")
    unknown = sorted(key for key in raw if key not in _WORK_KEYS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail="Только права scope=work: " + ", ".join(unknown),
        )
    if any(not isinstance(value, bool) for value in raw.values()):
        raise HTTPException(status_code=400, detail='Права должны быть логическими значениями')
    permissions = {key: value for key, value in raw.items() if value}
    return name, permissions


async def _assert_grantable(user, workspace_id: int, permissions: dict) -> None:
    """Потолок (право выдающего) + кран доступности в этом окружении.

    Потолок считается по рабочим правам в ЭТОМ окружении: админ окружения вправе делегировать то, чем реально
    располагает в нём (например, выдать выбранным участникам право
    из своей кастомной роли). Отсутствующие рабочие права выдать нельзя.
    """
    from app.core.permissions import get_workspace_permissions
    ws_permissions = await get_workspace_permissions(user.id, workspace_id) or {}
    ceiling = {'all': True} if is_root_user(user) else ws_permissions
    # assert_within_ceiling сам пропускает суперадмина ('all'), кран ниже — для всех
    assert_within_ceiling(ceiling, permissions)
    if not permissions:
        return
    state = await grantable_features(user, workspace_id, keys=list(permissions))
    blocked = sorted(key for key in permissions if not state.get(key, True))
    if blocked:
        raise HTTPException(
            status_code=403,
            detail="Функции отключены краном доступности: " + ", ".join(blocked),
        )


async def _assert_role_editable(session, ctx, role_id: int) -> None:
    """Changing a shared profile must obey the same rank ladder as assignment."""
    if is_root_user(ctx['user']):
        return
    members = (await session.execute(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == ctx['workspace'].id,
        WorkspaceMember.custom_role_id == role_id,
    ))).scalars().all()
    if any(workspace_role_rank(member.role) >= workspace_role_rank(ctx['role']) for member in members):
        raise HTTPException(status_code=403, detail='Роль назначена вам или участнику не ниже вас. Изменить её может старший администратор.')


@router.get("/{workspace_id}/roles")
async def list_ws_roles(workspace_id: int, ctx=Depends(require_workspace_management("workspace_profiles"))):
    """Роли окружения + эффективные фичи (чекбоксы, отключённые краном, скрыты)."""
    async with async_session() as session:
        rows = (await session.execute(
            select(WorkspaceRole)
            .where(WorkspaceRole.workspace_id == ctx["workspace"].id)
            .order_by(WorkspaceRole.id)
        )).scalars().all()
        features = await grantable_features(ctx["user"], ctx["workspace"].id)
    return JSONResponse({
        "roles": [_role_to_dict(row) for row in rows],
        "features": features,
    })


@router.post("/{workspace_id}/roles", status_code=201)
async def create_ws_role(workspace_id: int, request: Request,
                         ctx=Depends(require_workspace_management("workspace_profiles"))):
    data = await read_object(request)
    name, permissions = _validate_payload(data)
    fields = validate_fields(data.get("field_access", {}))
    await assert_field_ceiling(ctx["user"], workspace_id, fields)
    await _assert_grantable(ctx["user"], ctx["workspace"].id, permissions)
    async with async_session() as session:
        existing = (await session.execute(
            select(WorkspaceRole).where(
                WorkspaceRole.workspace_id == ctx["workspace"].id,
                WorkspaceRole.name == name,
            )
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Роль с таким названием уже есть")
        role = WorkspaceRole(
            workspace_id=ctx["workspace"].id,
            name=name,
            field_access=json.dumps(fields),
            permissions=json.dumps(permissions, ensure_ascii=False),
        )
        session.add(role)
        await session.commit()
        await session.refresh(role)
    return JSONResponse(_role_to_dict(role), status_code=201)


@router.put("/{workspace_id}/roles/{role_id}")
async def update_ws_role(workspace_id: int, role_id: int, request: Request,
                         ctx=Depends(require_workspace_management("workspace_profiles"))):
    data = await read_object(request)
    async with async_session() as session:
        role = await session.get(WorkspaceRole, role_id)
        if role is None or role.workspace_id != ctx["workspace"].id:
            raise HTTPException(status_code=404, detail="Роль не найдена")
        await _assert_role_editable(session, ctx, role_id)
        if "field_access" in data:
            fields = validate_fields(data["field_access"])
            await assert_field_ceiling(ctx["user"], workspace_id, fields)
            role.field_access = json.dumps(fields)
        if "name" in data or "permissions" in data or "field_access" in data:
            name, _ = _validate_payload({'name': data.get('name', role.name)})
            if "permissions" in data:
                _, permissions = _validate_payload({"name": name, "permissions": data.get("permissions")})
                from app.core.permissions import get_workspace_permissions
                ceiling = {'all': True} if is_root_user(ctx['user']) else await get_workspace_permissions(ctx['user'].id, workspace_id) or {}
                assert_within_ceiling(ceiling, permissions)
                previous = _role_permissions(role)
                added = {key: True for key in permissions if not previous.get(key)}
                await _assert_grantable(ctx["user"], ctx["workspace"].id, added)
            else:
                permissions = _role_permissions(role)
            if name != role.name:
                clash = (await session.execute(
                    select(WorkspaceRole).where(
                        WorkspaceRole.workspace_id == ctx["workspace"].id,
                        WorkspaceRole.name == name,
                        WorkspaceRole.id != role_id,
                    )
                )).scalar_one_or_none()
                if clash:
                    raise HTTPException(status_code=400, detail="Роль с таким названием уже есть")
                role.name = name
            role.permissions = json.dumps(permissions, ensure_ascii=False)
            await session.commit()
        else:
            role = await session.get(WorkspaceRole, role_id)
    return JSONResponse(_role_to_dict(role))


@router.delete("/{workspace_id}/roles/{role_id}")
async def delete_ws_role(workspace_id: int, role_id: int,
                         ctx=Depends(require_workspace_management("workspace_profiles"))):
    async with async_session() as session:
        role = await session.get(WorkspaceRole, role_id)
        if role is None or role.workspace_id != ctx["workspace"].id:
            raise HTTPException(status_code=404, detail="Роль не найдена")
        assigned = (await session.execute(select(WorkspaceMember.user_id).where(
            WorkspaceMember.custom_role_id == role_id,
        ))).first()
        if assigned:
            raise HTTPException(status_code=409, detail='Роль назначена участникам. Сначала явно смените их профили доступа, затем удалите роль.')
        await session.delete(role)
        await session.commit()
    return JSONResponse({"ok": True})


@router.put("/{workspace_id}/members/{user_id}/custom-role")
async def assign_ws_role(workspace_id: int, user_id: int, request: Request,
                         ctx=Depends(require_workspace_management("workspace_profiles"))):
    """Назначение/снятие кастомной роли участнику (role_id=null → снять)."""
    data = await read_object(request)
    role_id = data.get("role_id")
    if role_id is not None and (isinstance(role_id, bool) or not isinstance(role_id, int) or role_id < 1):
        raise HTTPException(status_code=400, detail='role_id должен быть положительным целым числом или null')
    async with async_session() as session:
        member = (await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx["workspace"].id,
                WorkspaceMember.user_id == user_id,
            )
        )).scalar_one_or_none()
        if member is None:
            raise HTTPException(status_code=404, detail="Участник не найден")
        target = await session.get(User, user_id)
        if target is not None and target.is_root and not is_root_user(ctx["user"]):
            raise HTTPException(status_code=403, detail="Нельзя изменять root-пользователя")
        if not is_root_user(ctx["user"]):
            if workspace_role_rank(member.role) >= workspace_role_rank(ctx["role"]):
                raise HTTPException(
                    status_code=403,
                    detail="Профиль доступа можно назначать только участнику ниже вашей роли",
                )
        role_name = None
        if role_id is not None:
            role = await session.get(WorkspaceRole, int(role_id))
            if role is None or role.workspace_id != ctx["workspace"].id:
                raise HTTPException(status_code=404, detail="Роль не найдена")
            # выдавать можно только то, что вправе выдавать сам:
            # иначе админ раздаёт чужие привилегированные профили
            await _assert_grantable(ctx["user"], ctx["workspace"].id, _role_permissions(role))
            await assert_field_ceiling(ctx["user"], workspace_id, parse_policy(role.field_access))
            member.custom_role_id = role.id
            role_name = role.name
        else:
            # Returning to rank defaults is also a grant, not merely removing a link.
            from app.core.permission_catalog import workspace_default_permissions
            from app.core.permissions import get_workspace_permissions
            ceiling = {'all': True} if is_root_user(ctx['user']) else await get_workspace_permissions(ctx['user'].id, workspace_id) or {}
            assert_within_ceiling(ceiling, workspace_default_permissions(member.role))
            await assert_field_ceiling(ctx["user"], workspace_id, {})
            member.custom_role_id = None
        await session.commit()
        username = (await session.get(User, user_id)).username
    return JSONResponse({
        "user_id": user_id,
        "username": username,
        "role": member.role,
        "custom_role_id": member.custom_role_id,
        "custom_role": role_name,
        "created_at": member.created_at.isoformat() if member.created_at else None,
    })


async def grantable_features(user, workspace_id, keys=None):
    from app.core.permissions import get_global_feature_state
    from app.core.models import FeatureOverride
    state = await get_effective_features(user, workspace_id, keys)
    global_state = await get_global_feature_state(keys)
    async with async_session() as session:
        overrides = (await session.execute(select(FeatureOverride).where(FeatureOverride.scope == 'workspace', FeatureOverride.target_id == workspace_id))).scalars().all()
    for key in state:
        if not global_state.get(key, False):
            state[key] = False
    for row in overrides:
        if not row.enabled and row.key in state:
            state[row.key] = False
    return state
