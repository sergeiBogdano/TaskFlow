import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import async_session
from app.core.models import Module, Notification, Task
from app.core.permissions import require_role, get_current_user
from app.core.utils.timezone import format_datetime, to_utc, utc_now
from app.core.config import settings

router = APIRouter(prefix="/api/modules", tags=["modules"])


def _module_client_ids(module: Module) -> list[int]:
    ids: list[int] = []
    raw = getattr(module, 'client_ids', None)
    if raw:
        try:
            ids = [int(item) for item in json.loads(raw) if item]
        except Exception:
            ids = []
    if not ids and module.client_id:
        ids = [module.client_id]
    return ids


def _dump_client_ids(value) -> str:
    return json.dumps([int(item) for item in (value or []) if item], ensure_ascii=False)


def _validate_module_dates(completion_offset_days, deadline_offset_days):
    if deadline_offset_days is not None and completion_offset_days is not None and completion_offset_days > deadline_offset_days:
        raise HTTPException(status_code=400, detail='Дата выполнения модуля не может быть позже крайнего срока')


@router.get('')
async def list_modules(user=Depends(get_current_user)):
    async with async_session() as session:
        r = await session.execute(
            select(Module).options(selectinload(Module.client), selectinload(Module.assignee)).order_by(Module.id)
        )
        modules = r.scalars().all()
    return JSONResponse([{
        'id': m.id,
        'name': m.name,
        'description': m.description or '',
        'client_id': m.client_id,
        'client_ids': _module_client_ids(m),
        'client': m.client.org_name if m.client else (f"{len(_module_client_ids(m))} организаций" if _module_client_ids(m) else ''),
        'assignee_id': m.assignee_id,
        'assignee': m.assignee.username if m.assignee else '',
        'recurring_interval': m.recurring_interval,
        'recurring_day': m.recurring_day,
        'recurring_count': m.recurring_count,
        'task_title_template': m.task_title_template,
        'task_title_templates': json.loads(m.task_title_templates) if getattr(m, 'task_title_templates', None) else [],
        'completion_offset_days': getattr(m, 'completion_offset_days', 0) or 0,
        'deadline_offset_days': getattr(m, 'deadline_offset_days', None),
        'task_type': m.task_type,
        'task_priority': getattr(m, 'task_priority', 'medium') or 'medium',
        'task_notes_template': getattr(m, 'task_notes_template', '') or '',
        'is_active': m.is_active,
        'last_generated_at': format_datetime(getattr(m, 'last_generated_at', None), settings.tz) if getattr(m, 'last_generated_at', None) else '',
        'created_at': format_datetime(m.created_at, settings.tz) if m.created_at else '',
    } for m in modules])


@router.post('')
async def create_module(data: dict, user=Depends(require_role(['superadmin', 'admin']))):
    _validate_module_dates(data.get('completion_offset_days', 0), data.get('deadline_offset_days'))
    client_ids = [int(item) for item in (data.get('client_ids') or []) if item]
    if not client_ids and data.get('client_id'):
        client_ids = [int(data.get('client_id'))]
    async with async_session() as session:
        m = Module(
            name=data['name'],
            description=data.get('description'),
            client_id=client_ids[0] if client_ids else None,
            client_ids=_dump_client_ids(client_ids),
            assignee_id=data.get('assignee_id'),
            recurring_interval=data.get('recurring_interval'),
            recurring_day=data.get('recurring_day'),
            recurring_count=data.get('recurring_count', 1),
            task_title_template=data.get('task_title_template'),
            task_title_templates=json.dumps(data.get('task_title_templates') or [], ensure_ascii=False),
            completion_offset_days=data.get('completion_offset_days', 0),
            deadline_offset_days=data.get('deadline_offset_days'),
            task_type=data.get('task_type', 'custom'),
            task_priority=data.get('task_priority', 'medium'),
            task_notes_template=data.get('task_notes_template'),
        )
        session.add(m)
        await session.commit()
        await session.refresh(m)
    return JSONResponse({'id': m.id, 'name': m.name}, status_code=201)


@router.put('/{module_id}')
async def update_module(module_id: int, data: dict, user=Depends(require_role(['superadmin', 'admin']))):
    async with async_session() as session:
        m = await session.get(Module, module_id)
        if not m:
            raise HTTPException(status_code=404, detail='Module not found')
        next_completion_offset = data.get('completion_offset_days', getattr(m, 'completion_offset_days', 0) or 0)
        next_deadline_offset = data.get('deadline_offset_days', getattr(m, 'deadline_offset_days', None))
        _validate_module_dates(next_completion_offset, next_deadline_offset)
        if 'task_title_templates' in data:
            m.task_title_templates = json.dumps(data.get('task_title_templates') or [], ensure_ascii=False)
        if 'client_ids' in data:
            m.client_ids = _dump_client_ids(data.get('client_ids'))
            ids = _module_client_ids(m)
            m.client_id = ids[0] if ids else data.get('client_id')
        for field in ['name', 'description', 'client_id', 'assignee_id', 'recurring_interval', 'recurring_day', 'recurring_count', 'task_title_template', 'completion_offset_days', 'deadline_offset_days', 'task_type', 'task_priority', 'task_notes_template', 'is_active']:
            if field in data:
                setattr(m, field, data[field])
        if 'client_ids' in data:
            ids = _module_client_ids(m)
            m.client_id = ids[0] if ids else None
        await session.commit()
    return JSONResponse({'ok': True})


@router.delete('/{module_id}')
async def delete_module(module_id: int, user=Depends(require_role(['superadmin', 'admin']))):
    async with async_session() as session:
        m = await session.get(Module, module_id)
        if m:
            await session.delete(m)
            await session.commit()
    return JSONResponse({'ok': True})


@router.post('/{module_id}/generate')
async def generate_tasks(module_id: int, data: dict = None, user=Depends(require_role(['superadmin', 'admin', 'manager']))):
    async with async_session() as session:
        m = await session.get(Module, module_id)
        if not m:
            raise HTTPException(status_code=404, detail='Module not found')
        count = data.get('count', 1) if data else 1
        templates = []
        if getattr(m, 'task_title_templates', None):
            try:
                templates = [item for item in json.loads(m.task_title_templates) if item]
            except Exception:
                templates = []
        if not templates:
            templates = [m.task_title_template or m.name]
        now = utc_now()
        completion_date = now + timedelta(days=int(getattr(m, 'completion_offset_days', 0) or 0))
        deadline_offset = getattr(m, 'deadline_offset_days', None)
        deadline = (now + timedelta(days=int(deadline_offset))) if deadline_offset is not None else None
        created = []
        created = []
        for client_id in (_module_client_ids(m) or [None]):
            for i in range(count):
                template = templates[i % len(templates)]
                suffix = f' #{i + 1}' if count > 1 else ''
                t = Task(
                    title=f'{template}{suffix}',
                    client_id=client_id,
                    assignee_id=m.assignee_id,
                    module_id=m.id,
                    task_type=m.task_type,
                    priority=getattr(m, 'task_priority', 'medium') or 'medium',
                    status='todo',
                    completion_date=completion_date,
                    deadline=deadline,
                    creator_id=user.id,
                    notes=getattr(m, 'task_notes_template', None),
                )
                session.add(t)
                if m.assignee_id and m.assignee_id != user.id:
                    session.add(Notification(
                        task=t,
                        client_id=client_id,
                        user_id=m.assignee_id,
                        notification_type='assigned',
                        title=f'Новая задача по модулю: {t.title}',
                        message='Задача создана автоматически по правилу модуля.',
                        trigger_at=now,
                    ))
                created.append(t)
        m.last_generated_at = now
        await session.commit()
    return JSONResponse({'ok': True, 'count': len(created)})
