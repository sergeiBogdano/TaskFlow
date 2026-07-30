import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select

from app.core.database import async_session
from app.core.models import SavedView
from app.core.permissions import get_current_user, get_user_role_names
from app.core.utils.timezone import format_datetime
from app.core.config import settings

router = APIRouter(prefix="/api/saved-views", tags=["saved-views"])


def _view_to_dict(view: SavedView) -> dict:
    return {
        'id': view.id,
        'user_id': view.user_id,
        'name': view.name,
        'view_type': view.view_type,
        'filters': json.loads(view.filters_json or '{}'),
        'sort_field': view.sort_field,
        'sort_order': view.sort_order,
        'created_at': format_datetime(view.created_at, settings.tz) if view.created_at else '',
    }


@router.get('')
async def list_saved_views(view_type: str = 'tasks', user=Depends(get_current_user)):
    async with async_session() as session:
        views = (await session.execute(
            select(SavedView).where(
                SavedView.view_type == view_type,
                or_(SavedView.user_id == user.id, SavedView.user_id.is_(None)),
            ).order_by(SavedView.created_at.desc())
        )).scalars().all()
    return JSONResponse([_view_to_dict(view) for view in views])


@router.post('')
async def create_saved_view(data: dict, user=Depends(get_current_user)):
    name = (data.get('name') or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='Name is required')
    async with async_session() as session:
        view = SavedView(
            user_id=user.id,
            name=name,
            view_type=data.get('view_type') or 'tasks',
            filters_json=json.dumps(data.get('filters') or {}, ensure_ascii=False),
            sort_field=data.get('sort_field'),
            sort_order=data.get('sort_order') or 'desc',
        )
        session.add(view)
        await session.commit()
        await session.refresh(view)
    return JSONResponse(_view_to_dict(view), status_code=201)


@router.put('/{view_id}')
async def update_saved_view(view_id: int, data: dict, user=Depends(get_current_user)):
    async with async_session() as session:
        view = await session.get(SavedView, view_id)
        if not view:
            raise HTTPException(status_code=404, detail='Saved view not found')
        roles = await get_user_role_names(user.id)
        if view.user_id not in (None, user.id) and not ({'superadmin', 'admin'} & roles):
            raise HTTPException(status_code=403, detail='Forbidden')
        if 'name' in data and data['name']:
            view.name = data['name']
        if 'filters' in data:
            view.filters_json = json.dumps(data.get('filters') or {}, ensure_ascii=False)
        if 'sort_field' in data:
            view.sort_field = data.get('sort_field')
        if 'sort_order' in data:
            view.sort_order = data.get('sort_order') or 'desc'
        await session.commit()
        await session.refresh(view)
    return JSONResponse(_view_to_dict(view))


@router.delete('/{view_id}')
async def delete_saved_view(view_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        view = await session.get(SavedView, view_id)
        if view:
            roles = await get_user_role_names(user.id)
            if view.user_id not in (None, user.id) and not ({'superadmin', 'admin'} & roles):
                raise HTTPException(status_code=403, detail='Forbidden')
            await session.delete(view)
            await session.commit()
    return JSONResponse({'ok': True})
