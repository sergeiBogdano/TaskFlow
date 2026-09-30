"""Кастомные роли окружения (Ф7): CRUD + назначение участнику.

Только scope=work-ключи, кран доступности (Ф6) и потолок (Ф3/Ф4).
Базовые rank owner/admin/member сохраняются — кастомная роль аддитивна.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update

from app.core.database import async_session
from app.core.models import User, WorkspaceMember, WorkspaceRole
from app.core.permission_catalog import work_scope_keys
from app.core.permissions import (
    assert_within_ceiling,
    get_effective_features,
    get_user_permissions,
    require_workspace_role,
)

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
        "created_at": role.created_at.isoformat() if role.created_at else None,
    }


def _validate_payload(data: dict) -> tuple[str, dict]:
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название роли")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="Название роли длиннее 100 символов")
    raw = data.get("permissions") or {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="permissions должен быть объектом")
    unknown = sorted(key for key in raw if key not in _WORK_KEYS)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail="Только права scope=work: " + ", ".join(unknown),
        )
    permissions = {key: bool(value) for key, value in raw.items() if value}
    return name, permissions


async def _assert_grantable(user, workspace_id: int, permissions: dict) -> None:
    """Потолок (право выдающего) + кран доступности в этом окружении."""
    assert_within_ceiling(await get_user_permissions(user.id), permissions)
    if not permissions:
        return
    state = await get_effective_features(user, workspace_id, keys=list(permissions))
    blocked = sorted(key for key in permissions if not state.get(key, True))
    if blocked:
        raise HTTPException(
            status_code=403,
            detail="Функции отключены краном доступности: " + ", ".join(blocked),
        )


@router.get("/{workspace_id}/roles")
async def list_ws_roles(workspace_id: int, ctx=Depends(require_workspace_role("owner", "admin"))):
    """Роли окружения + эффективные фичи (чекбоксы, отключённые краном, скрыты)."""
    async with async_session() as session:
        rows = (await session.execute(
            select(WorkspaceRole)
            .where(WorkspaceRole.workspace_id == ctx["workspace"].id)
            .order_by(WorkspaceRole.id)
        )).scalars().all()
        features = await get_effective_features(ctx["user"], ctx["workspace"].id)
    return JSONResponse({
        "roles": [_role_to_dict(row) for row in rows],
        "features": features,
    })


@router.post("/{workspace_id}/roles", status_code=201)
async def create_ws_role(workspace_id: int, request: Request,
                         ctx=Depends(require_workspace_role("owner", "admin"))):
    name, permissions = _validate_payload(await request.json())
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
            permissions=json.dumps(permissions, ensure_ascii=False),
        )
        session.add(role)
        await session.commit()
        await session.refresh(role)
    return JSONResponse(_role_to_dict(role), status_code=201)


@router.put("/{workspace_id}/roles/{role_id}")
async def update_ws_role(workspace_id: int, role_id: int, request: Request,
                         ctx=Depends(require_workspace_role("owner", "admin"))):
    data = await request.json()
    async with async_session() as session:
        role = await session.get(WorkspaceRole, role_id)
        if role is None or role.workspace_id != ctx["workspace"].id:
            raise HTTPException(status_code=404, detail="Роль не найдена")
        if "name" in data or "permissions" in data:
            name = (data.get("name") or role.name).strip()
            if not name:
                raise HTTPException(status_code=400, detail="Укажите название роли")
            if "permissions" in data:
                _, permissions = _validate_payload({"name": name, "permissions": data.get("permissions")})
                await _assert_grantable(ctx["user"], ctx["workspace"].id, permissions)
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
                         ctx=Depends(require_workspace_role("owner", "admin"))):
    async with async_session() as session:
        role = await session.get(WorkspaceRole, role_id)
        if role is None or role.workspace_id != ctx["workspace"].id:
            raise HTTPException(status_code=404, detail="Роль не найдена")
        # снятие назначений до удаления (sqlite может не применять ON DELETE SET NULL)
        await session.execute(
            update(WorkspaceMember)
            .where(WorkspaceMember.custom_role_id == role_id)
            .values(custom_role_id=None)
        )
        await session.delete(role)
        await session.commit()
    return JSONResponse({"ok": True})


@router.put("/{workspace_id}/members/{user_id}/custom-role")
async def assign_ws_role(workspace_id: int, user_id: int, request: Request,
                         ctx=Depends(require_workspace_role("owner", "admin"))):
    """Назначение/снятие кастомной роли участнику (role_id=null → снять)."""
    data = await request.json()
    role_id = data.get("role_id")
    async with async_session() as session:
        member = (await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ctx["workspace"].id,
                WorkspaceMember.user_id == user_id,
            )
        )).scalar_one_or_none()
        if member is None:
            raise HTTPException(status_code=404, detail="Участник не найден")
        role_name = None
        if role_id is not None:
            role = await session.get(WorkspaceRole, int(role_id))
            if role is None or role.workspace_id != ctx["workspace"].id:
                raise HTTPException(status_code=404, detail="Роль не найдена")
            member.custom_role_id = role.id
            role_name = role.name
        else:
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
