from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import FeatureOverride
from app.core.permissions import (
    get_current_user,
    get_effective_features,
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
            'items': [{'key': item['key'], 'label': item['label'], 'hint': item['hint']}
                      for item in group['items']],
        }
        for group in PERMISSION_GROUPS
    ]


@router.get('')
async def get_features(request: Request, user=Depends(require_root())):
    """Эффективный набор функций текущего пользователя/окружения + записи крана."""
    workspace_id = workspace_id_from_request(request)
    effective = await get_effective_features(user, workspace_id)
    async with async_session() as session:
        rows = (await session.execute(
            select(FeatureOverride).order_by(FeatureOverride.id)
        )).scalars().all()
    return JSONResponse({
        'catalog': _features_payload(),
        'effective': effective,
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
    data = await request.json()
    scope = data.get('scope') or 'global'
    key = (data.get('key') or '').strip()
    # enabled=null → убрать запись крана (вернуться к более верхнему уровню)
    drop = 'enabled' in data and data.get('enabled') is None
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
        target_id = int(target_id)
        if scope == 'group':
            from app.core.models import Group
            async with async_session() as session:
                if not await session.get(Group, target_id):
                    raise HTTPException(status_code=404, detail='Группа не найдена')
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
        await session.commit()
    return JSONResponse({'ok': True})
