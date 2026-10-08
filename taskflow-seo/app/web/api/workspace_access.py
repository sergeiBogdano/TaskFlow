"""A single, explainable access report and personal exceptions per workspace."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.core.access_policy import (
    assert_field_ceiling, field_access, field_catalog_payload, parse_policy, validate_fields,
)
from app.core.database import async_session
from app.core.models import User, WorkspaceMember, WorkspaceRole
from app.core.permission_catalog import PERMISSION_GROUPS, work_scope_keys
from app.core.permissions import (
    assert_within_ceiling, get_feature_access, get_workspace_permissions,
    require_workspace_management, workspace_role_rank,
)
from app.web.api.access_validation import read_object, validate_permissions

router = APIRouter(prefix='/api/workspaces', tags=['workspace-access'])


async def _report(member, user, role, workspace_id):
    permissions = await get_workspace_permissions(user.id, workspace_id) or {}
    features = await get_feature_access(user, workspace_id)
    overrides = parse_policy(member.access_overrides)
    fields = await field_access(user, workspace_id)
    return {
        'user_id': user.id, 'username': user.username, 'is_root': user.is_root,
        'level': member.role, 'profile_id': member.custom_role_id,
        'profile': role.name if role else 'Стандартный профиль уровня',
        'overrides': overrides, 'fields': fields,
        'permissions': {key: {
            'granted': user.is_root or bool(permissions.get(key)),
            'available': bool(features.get(key, {}).get('available')),
            'allowed': bool((user.is_root or permissions.get(key)) and features.get(key, {}).get('available')),
            'source': 'Суперадмин' if user.is_root else 'Личное исключение' if key in overrides.get('permissions', {}) else 'Профиль доступа' if role else 'Стандартный профиль уровня',
            'reason': '; '.join(filter(None, [features.get(key, {}).get('reason'), '' if user.is_root or permissions.get(key) else 'Нет права: включите его в рабочем профиле или личном исключении'])) or 'Разрешено',
        } for key in work_scope_keys()},
    }


@router.get('/{workspace_id}/access')
async def access_report(workspace_id: int, ctx=Depends(require_workspace_management('workspace_profiles'))):
    async with async_session() as session:
        members = (await session.execute(select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id).order_by(WorkspaceMember.id))).scalars().all()
        rows = []
        for member in members:
            user = await session.get(User, member.user_id)
            role = await session.get(WorkspaceRole, member.custom_role_id) if member.custom_role_id else None
            if user:
                rows.append(await _report(member, user, role, workspace_id))
    return {'members': rows, 'fields': field_catalog_payload(),
            'groups': [group for group in PERMISSION_GROUPS if group['scope'] == 'work']}


@router.put('/{workspace_id}/members/{user_id}/access')
async def set_personal_access(workspace_id: int, user_id: int, request: Request,
                              ctx=Depends(require_workspace_management('workspace_profiles'))):
    data = await read_object(request)
    if set(data) - {'permissions', 'fields'}:
        raise HTTPException(400, 'Допустимы только permissions и fields')
    permissions = validate_permissions(data.get('permissions', {}))
    if set(permissions) - set(work_scope_keys()):
        raise HTTPException(400, 'Права приложения не назначаются в окружении')
    fields = validate_fields(data.get('fields', {}))
    async with async_session() as session:
        member = (await session.execute(select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id))).scalar_one_or_none()
        target = await session.get(User, user_id)
        if member is None or target is None:
            raise HTTPException(404, 'Участник не найден')
        actor = ctx['user']
        if target.is_root or target.id == actor.id:
            raise HTTPException(403, 'Root и собственный доступ не изменяются через личные исключения')
        if not actor.is_root and workspace_role_rank(member.role) >= workspace_role_rank(ctx['role']):
            raise HTTPException(403, 'Можно изменять только участников ниже своего уровня')
        ceiling = {'all': True} if actor.is_root else await get_workspace_permissions(actor.id, workspace_id) or {}
        from app.core.permission_catalog import workspace_default_permissions
        target_profile = await session.get(WorkspaceRole, member.custom_role_id) if member.custom_role_id else None
        base_permissions = parse_policy(target_profile.permissions) if target_profile else workspace_default_permissions(member.role)
        next_permissions = {**base_permissions, **permissions}
        previous_permissions = await get_workspace_permissions(target.id, workspace_id) or {}
        granted = {key: True for key, value in next_permissions.items() if value and (not previous_permissions.get(key) or permissions.get(key))}
        assert_within_ceiling(ceiling, granted)
        from app.web.api.workspace_roles import grantable_features
        available = await grantable_features(actor, workspace_id)
        if any(not available.get(key, False) for key in granted):
            raise HTTPException(403, 'Нельзя выдать отключённую функцию')
        profile = await session.get(WorkspaceRole, member.custom_role_id) if member.custom_role_id else None
        from app.core.access_policy import FIELD_CATALOG, LEGACY_FIELDS
        baseline = {entity: {key: 'edit' if key in LEGACY_FIELDS[entity] else 'hidden' for key in values} for entity, values in FIELD_CATALOG.items()}
        for entity, values in (parse_policy(profile.field_access) if profile else {}).items():
            baseline[entity].update(values)
        await assert_field_ceiling(actor, workspace_id, fields, baseline=baseline)
        member.access_overrides = json.dumps({'permissions': permissions, 'fields': fields}, ensure_ascii=False)
        await session.commit()
    from app.core.cache import dashboard_cache
    dashboard_cache.clear()
    from app.services.activity_service import log_activity
    await log_activity('workspace', workspace_id, 'access_changed', actor_user_id=ctx['user'].id, summary=f'Изменены личные исключения участника #{user_id}')
    return {'ok': True}
