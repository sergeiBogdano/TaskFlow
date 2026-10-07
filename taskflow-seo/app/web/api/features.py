from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.web.api.access_validation import read_object
from app.core.database import async_session
from app.core.models import FeatureOverride
from app.core.permissions import (
    get_current_user,
    get_effective_features,
    get_global_feature_state,
    require_root,
    workspace_id_from_request,
)
from app.core.permission_catalog import PERMISSION_GROUPS

router = APIRouter(prefix='/api/features', tags=['features'])

SCOPES = ('global', 'workspace', 'group', 'user')

# защита от самоблокировки: на этом ключе держится сама панель «Функции»
PROTECTED_KEYS = {'settings'}


def _features_payload() -> list[dict]:
    return [
        {
            'id': group['id'],
            'scope': group['scope'],
            'title': group['title'],
            'description': group['description'],
            'items': [{'key': item['key'], 'label': item['label'], 'hint': item.get('hint', '')}
                      for item in group['items']],
        }
        for group in PERMISSION_GROUPS
    ]


@router.get('')
async def get_features(request: Request, scope: str = 'global', target_id: int | None = Query(default=None), user=Depends(require_root())):
    """Эффективный набор функций текущего пользователя/окружения + записи крана."""
    workspace_id = workspace_id_from_request(request)
    effective = await get_effective_features(user, workspace_id)
    if scope not in SCOPES:
        raise HTTPException(status_code=400, detail='Неизвестная область функций')
    scope_state = await get_global_feature_state()
    async with async_session() as session:
        rows = (await session.execute(
            select(FeatureOverride).order_by(FeatureOverride.id)
        )).scalars().all()
        if scope != 'global':
            from app.core.models import Group, Workspace, User
            model = {'group': Group, 'workspace': Workspace, 'user': User}[scope]
            target = await session.get(model, target_id) if target_id is not None else None
            if target is None:
                raise HTTPException(status_code=404, detail='Объект настройки функций не найден')
            if scope == 'user':
                scope_state = await get_effective_features(target, workspace_id)
            else:
                for row in rows:
                    if row.scope == scope and row.target_id == target_id:
                        scope_state[row.key] = bool(row.enabled) and scope_state.get(row.key, False)
                if scope == 'workspace':
                    import json
                    from app.core.workspace_modules import module_for_permission
                    modules = json.loads(target.enabled_modules or '[]')
                    scope_state = {key: value and (not module_for_permission(key) or module_for_permission(key) in modules) for key, value in scope_state.items()}
    return JSONResponse({
        'catalog': _features_payload(),
        'effective': effective,
        'scope_effective': scope_state,
        'overrides': [{
            'id': row.id,
            'scope': row.scope,
            'target_id': row.target_id,
            'key': row.key,
            'enabled': bool(row.enabled),
        } for row in rows],
    })


@router.put('')
async def set_feature(request: Request, user=Depends(require_root())):
    """Тумблер крана: upsert записи global|workspace|group|user (приоритет user>ws>group>global), enabled=null → убрать запись."""
    data = await read_object(request)
    scope = data.get('scope') or 'global'
    key = (data.get('key') or '').strip()
    # enabled=null → убрать запись крана (вернуться к более верхнему уровню)
    drop = 'enabled' in data and data.get('enabled') is None
    if not drop and not isinstance(data.get('enabled'), bool):
        raise HTTPException(status_code=400, detail='enabled должен быть логическим значением или null')
    enabled = bool(data.get('enabled'))
    target_id = data.get('target_id')
    if scope not in SCOPES:
        raise HTTPException(status_code=400, detail=f'Область: {", ".join(SCOPES)}')
    if not key or key not in {item['key'] for g in PERMISSION_GROUPS for item in g['items']}:
        raise HTTPException(status_code=400, detail='Неизвестная функция')
    if key in PROTECTED_KEYS and not enabled and not drop:
        raise HTTPException(status_code=400, detail='Эту функцию нельзя выключить — на ней держится сама панель управления')
    if scope == 'global':
        target_id = None
    else:
        if target_id is None:
            raise HTTPException(status_code=400, detail='target_id обязателен для этой области')
        if isinstance(target_id, bool) or not isinstance(target_id, int) or target_id < 1:
            raise HTTPException(status_code=400, detail='target_id должен быть положительным целым числом')
        if scope in ('group', 'workspace', 'user'):
            from app.core.models import Group, Workspace, User
            async with async_session() as session:
                model = {'group': Group, 'workspace': Workspace, 'user': User}[scope]
                if not await session.get(model, target_id):
                    raise HTTPException(status_code=404, detail='Объект настройки функций не найден')
    async with async_session() as session:
        stmt = select(FeatureOverride).where(
            FeatureOverride.scope == scope,
            FeatureOverride.key == key,
        )
        if target_id is None:
            stmt = stmt.where(FeatureOverride.target_id.is_(None))
        else:
            stmt = stmt.where(FeatureOverride.target_id == target_id)
        row = (await session.execute(stmt)).scalars().first()
        if row and drop:
            await session.delete(row)
        elif row:
            row.enabled = enabled
        elif not drop:
            session.add(FeatureOverride(scope=scope, target_id=target_id, key=key, enabled=enabled))
        if scope == 'global' and not enabled and not drop:
            # Restore makes the feature available for explicit opt-in, never revives old user access.
            from app.core.models import User
            for uid in (await session.execute(select(User.id).where(User.is_root.is_(False)))).scalars():
                existing = (await session.execute(select(FeatureOverride).where(FeatureOverride.scope == 'user', FeatureOverride.target_id == uid, FeatureOverride.key == key))).scalars().first()
                if existing:
                    existing.enabled = False
                else:
                    session.add(FeatureOverride(scope='user', target_id=uid, key=key, enabled=False))
        await session.commit()
    from app.core.cache import dashboard_cache
    dashboard_cache.clear()
    return JSONResponse({'ok': True})
