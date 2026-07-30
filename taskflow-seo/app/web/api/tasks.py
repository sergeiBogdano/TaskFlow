import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.database import async_session
from app.core.models import Client, FileAttachment, Notification, Task, TaskCoExecutor, TaskComment
from app.core.permissions import (
    client_is_visible_to_user,
    get_accessible_client_ids,
    get_current_user,
    get_user_permissions,
    get_user_role_names,
    task_is_editable_by_user,
    task_is_visible_to_user,
    user_is_superadmin,
)
from app.core.utils.timezone import format_datetime, safe_dt, to_utc, utc_now
from app.core.config import settings
from app.services.activity_service import list_activity, log_activity
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

TASK_FIELD_LABELS = {
    'title': 'Название',
    'status': 'Статус',
    'priority': 'Приоритет',
    'task_type': 'Тип задачи',
    'client_id': 'Клиент',
    'notes': 'Описание',
    'comment': 'Выполненные работы',
    'assignee_id': 'Исполнитель',
    'co_executor_ids': 'Соисполнители',
    'deadline': 'Крайний срок',
    'completion_date': 'Дата выполнения',
    'no_contract': 'Нет договора',
    'visibility': 'Видимость',
    'client_access_ids': 'Доступы клиента',
    'checklist': 'Чек-лист',
}


def _parse_iso_datetime(value):
    if not value:
        return None
    from datetime import datetime

    return to_utc(datetime.fromisoformat(value))


def _activity_value(value):
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return json.dumps(sorted(value), ensure_ascii=False)
    return str(value)


def _validate_task_dates(completion_date, deadline):
    if completion_date and deadline and completion_date > deadline:
        raise HTTPException(status_code=400, detail='Дата выполнения не может быть позже крайнего срока')


async def _validate_contract_task_dates(session, client_id: int | None, no_contract: bool | None, *dates):
    checked_dates = [safe_dt(value) for value in dates if value]
    if no_contract or client_id is None or not checked_dates:
        return
    from app.core.models import Client

    result = await session.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if client and client.contract_end:
        contract_end = safe_dt(client.contract_end)
        if contract_end and any(contract_end < value for value in checked_dates):
            raise HTTPException(status_code=400, detail='Срок задачи не может быть позже окончания договора клиента')


async def _ensure_client_access(session, acting_user, role_names: set[str], accessible_client_ids: set[int], client_id: int | None):
    if client_id is None or user_is_superadmin(role_names):
        return
    if not client_is_visible_to_user(client_id, role_names, accessible_client_ids):
        raise HTTPException(status_code=403, detail='Нет доступа к клиенту')


def _normalize_co_executor_ids(data: dict, fallback=None) -> list[int]:
    raw = data.get('co_executor_ids', fallback)
    if raw is None:
        single = data.get('co_executor_id')
        raw = [single] if single else []
    ids: list[int] = []
    for value in raw or []:
        if value in (None, ''):
            continue
        user_id = int(value)
        if user_id not in ids:
            ids.append(user_id)
    return ids


async def _set_task_co_executors(session, task: Task, co_executor_ids: list[int]):
    await session.execute(sa_delete(TaskCoExecutor).where(TaskCoExecutor.task_id == task.id))
    for user_id in co_executor_ids:
        session.add(TaskCoExecutor(task_id=task.id, user_id=user_id))
    task.co_executor_id = co_executor_ids[0] if co_executor_ids else None


def _assignment_user_ids(assignee_id: int | None, co_executor_ids: list[int] | None = None) -> set[int]:
    ids = {int(assignee_id)} if assignee_id else set()
    ids.update(int(user_id) for user_id in (co_executor_ids or []) if user_id)
    return ids


def _co_executor_exists_for(user_id: int):
    return select(TaskCoExecutor.id).where(
        TaskCoExecutor.task_id == Task.id,
        TaskCoExecutor.user_id == user_id,
    ).exists()


def _participant_condition(user_id: int):
    return or_(
        Task.creator_id == user_id,
        Task.assignee_id == user_id,
        Task.co_executor_id == user_id,
        _co_executor_exists_for(user_id),
    )


def _parse_scope_user_ids(value) -> list[int]:
    if value in (None, ''):
        return []
    values = value if isinstance(value, (list, tuple, set)) else str(value).split(',')
    result: list[int] = []
    for item in values:
        try:
            user_id = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if user_id and user_id not in result:
            result.append(user_id)
    return result


def _task_scope_condition(scope: str, current_user_id: int, role_names: set[str], permissions: dict, scope_user_id=None):
    can_view_all = user_is_superadmin(role_names) or permissions.get('all') or permissions.get('tasks_view_all') or permissions.get('tasks_view_others')
    can_view_team = can_view_all or permissions.get('tasks_view_team')
    scope = scope or 'mine'
    if scope == 'all':
        return None if can_view_all else Task.assignee_id == current_user_id
    if scope == 'user':
        scope_user_ids = _parse_scope_user_ids(scope_user_id)
        if can_view_team and scope_user_ids:
            return or_(*[_participant_condition(user_id) for user_id in scope_user_ids])
        return _participant_condition(current_user_id)
    if scope in {'mine', 'assigned'}:
        return Task.assignee_id == current_user_id
    if scope == 'coassigned':
        return or_(Task.co_executor_id == current_user_id, _co_executor_exists_for(current_user_id))
    if scope == 'created':
        return Task.creator_id == current_user_id
    if scope == 'involved':
        return _participant_condition(current_user_id)
    return Task.assignee_id == current_user_id


async def _add_assignment_notifications(session, task: Task, actor_user_id: int | None, target_user_ids: set[int]):
    for target_user_id in sorted(target_user_ids):
        if not target_user_id or target_user_id == actor_user_id:
            continue
        session.add(Notification(
            task_id=task.id,
            client_id=task.client_id,
            user_id=target_user_id,
            notification_type='assigned',
            title=f'Новая задача #{task.id}',
            message=f'Вам назначена задача: {task.title}',
            trigger_at=utc_now(),
        ))


async def _ensure_assignees_valid_for_client(session, role_names: set[str], client_id: int | None, assignee_id: int | None, co_executor_ids):
    co_executor_ids = [int(user_id) for user_id in (co_executor_ids or []) if user_id]
    if assignee_id and assignee_id in co_executor_ids:
        raise HTTPException(status_code=400, detail='Исполнитель и соисполнитель должны быть разными')
    if len(co_executor_ids) != len(set(co_executor_ids)):
        raise HTTPException(status_code=400, detail='Соисполнители не должны повторяться')
    # Client access controls sensitive client tabs. It must not block a task
    # assignment when organizations are shared across the team.


async def _validate_contract_deadline(session, client_id: int | None, deadline, no_contract: bool | None):
    if no_contract or client_id is None or deadline is None:
        return
    from app.core.models import Client
    from app.core.utils.timezone import safe_dt
    result = await session.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if client and client.contract_end:
        contract_end = safe_dt(client.contract_end)
        if contract_end < deadline:
            raise HTTPException(status_code=400, detail='Договор истекает раньше дедлайна')


def _task_to_dict(t: Task) -> dict:
    dl = safe_dt(t.deadline)
    cd = safe_dt(t.completion_date)
    client_name = t.client.org_name if t.client else ''
    client_warning = t.client.client_warning if t.client else ''
    co_executor_ids = [link.user_id for link in getattr(t, 'co_executor_links', []) or [] if link.user_id]
    if t.co_executor_id and t.co_executor_id not in co_executor_ids:
        co_executor_ids.insert(0, t.co_executor_id)
    return {
        'id': t.id,
        'title': t.title,
        'status': t.status,
        'priority': t.priority,
        'task_type': t.task_type,
        'client': client_name,
        'client_id': t.client_id,
        'client_warning': client_warning or '',
        'notes': t.notes or '',
        'comment': t.comment or '',
        'deadline': dl.isoformat() if dl else None,
        'completion_date': cd.isoformat() if cd else None,
        'checklist': t.checklist or [],
        'sort_order': t.sort_order or 0,
        'created_at': safe_dt(t.created_at).isoformat() if t.created_at else '',
        'updated_at': safe_dt(t.updated_at).isoformat() if t.updated_at else '',
        'recurring_interval': t.recurring_interval,
        'recurring_count': t.recurring_count,
        'recurring_remaining': t.recurring_remaining,
        'creator_id': t.creator_id,
        'assignee_id': t.assignee_id,
        'co_executor_id': t.co_executor_id,
        'co_executor_ids': co_executor_ids,
        'no_contract': t.no_contract or False,
        'module_id': t.module_id,
        'visibility': t.visibility or 'public',
        'client_access_ids': json.loads(t.client_access_ids) if isinstance(t.client_access_ids, str) and t.client_access_ids else [],
        'deleted_at': safe_dt(t.deleted_at).isoformat() if t.deleted_at else None,
    }


def _client_accesses_for_task(task: Task) -> list[dict]:
    selected_ids = set()
    if isinstance(task.client_access_ids, str) and task.client_access_ids:
        try:
            selected_ids = {int(item) for item in json.loads(task.client_access_ids or '[]') if item}
        except (TypeError, ValueError, json.JSONDecodeError):
            selected_ids = set()
    if not task.client or not task.client.accesses or not selected_ids:
        return []
    try:
        raw_accesses = json.loads(task.client.accesses) if isinstance(task.client.accesses, str) else task.client.accesses
    except json.JSONDecodeError:
        return []
    result = []
    for index, access in enumerate(raw_accesses or [], start=1):
        if not isinstance(access, dict):
            continue
        access_id = int(access.get('id') or index)
        if access_id in selected_ids:
            result.append({**access, 'id': access_id})
    return result


async def _load_task_for_response(session, task_id: int) -> Task | None:
    result = await session.execute(
        select(Task).options(
            selectinload(Task.client),
            selectinload(Task.co_executor_links),
        ).where(Task.id == task_id)
    )
    return result.scalar_one_or_none()


@router.get('')
@router.get('/all')
async def list_tasks(
    request: Request,
    status: str = Query(None),
    priority: str = Query(None),
    assignee: int = Query(None),
    client_id: int = Query(None),
    task_type: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    search: str = Query(None),
    scope: str = Query('mine'),
    scope_user_id: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    paginated: bool = Query(False),
    user=Depends(get_current_user),
):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        conditions = [Task.deleted_at.is_(None)]

        scope_condition = _task_scope_condition(scope, user.id, role_names, permissions, scope_user_id)
        if scope_condition is not None:
            conditions.append(scope_condition)

        if status:
            statuses = [item.strip() for item in status.split(',') if item.strip()]
            if statuses:
                conditions.append(Task.status.in_(statuses))
        if priority:
            conditions.append(Task.priority == priority)
        if assignee:
            conditions.append(Task.assignee_id == assignee)
        if client_id:
            conditions.append(Task.client_id == client_id)
        if task_type:
            conditions.append(Task.task_type == task_type)
        if date_from:
            from datetime import datetime
            conditions.append(Task.deadline >= datetime.fromisoformat(date_from))
        if date_to:
            from datetime import datetime
            conditions.append(Task.deadline <= datetime.fromisoformat(date_to))
        if search:
            needle = f'%{search.strip()}%'
            conditions.append(or_(
                Task.title.ilike(needle),
                Task.notes.ilike(needle),
                Task.comment.ilike(needle),
                Task.client.has(Client.org_name.ilike(needle)),
            ))

        total = (await session.execute(
            select(func.count(Task.id)).where(*conditions)
        )).scalar_one()
        query = select(Task).options(
            selectinload(Task.client),
            selectinload(Task.co_executor_links),
        ).where(*conditions).order_by(Task.id.desc())
        if paginated:
            query = query.offset((page - 1) * page_size).limit(page_size)
            page_tasks = list((await session.execute(query)).scalars().unique().all())
            return JSONResponse({
                'items': [_task_to_dict(t) for t in page_tasks],
                'total': total,
                'page': page,
                'page_size': page_size,
            })
        tasks = list((await session.execute(query)).scalars().unique().all())
        result = [_task_to_dict(t) for t in tasks]
    return JSONResponse(result)


@router.get('/trash')
async def list_trash(user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        result = await session.execute(
            select(Task).options(selectinload(Task.client))
            .where(Task.deleted_at.is_not(None))
            .order_by(Task.deleted_at.desc())
        )
        tasks = [
            _task_to_dict(task)
            for task in result.scalars().all()
            if task_is_visible_to_user(task, user, role_names, accessible_client_ids)
        ]
    return JSONResponse(tasks)


@router.post('/trash/empty')
async def empty_trash(user=Depends(get_current_user)):
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not ({'superadmin', 'admin'} & role_names):
            raise HTTPException(status_code=403, detail='Forbidden')
        trash_tasks = (await session.execute(
            select(Task).where(Task.deleted_at.is_not(None))
        )).scalars().all()
        count = len(trash_tasks)
        for task in trash_tasks:
            await session.execute(sa_delete(FileAttachment).where(FileAttachment.task_id == task.id))
            await session.delete(task)
        await session.commit()
    return JSONResponse({'ok': True, 'count': count})


@router.post('/bulk')
async def bulk_update_tasks(data: dict, user=Depends(get_current_user)):
    ids = [int(item) for item in (data.get('ids') or []) if item]
    fields = data.get('fields') or {}
    if not ids:
        raise HTTPException(status_code=400, detail='No tasks selected')

    allowed_statuses = {'todo', 'in_progress', 'waiting', 'client_check', 'done', 'overdue'}
    allowed_fields = {
        'status', 'priority', 'assignee_id', 'co_executor_id', 'co_executor_ids', 'client_id',
        'completion_date', 'deadline', 'visibility', 'no_contract', 'deleted',
    }
    unknown = set(fields) - allowed_fields
    if unknown:
        raise HTTPException(status_code=400, detail=f'Unsupported fields: {", ".join(sorted(unknown))}')
    if fields.get('status') and fields['status'] not in allowed_statuses:
        raise HTTPException(status_code=400, detail='Invalid status')

    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        result = await session.execute(select(Task).where(Task.id.in_(ids)))
        tasks = result.scalars().all()
        updated = 0

        for task in tasks:
            if not task_is_editable_by_user(task, user, role_names, accessible_client_ids):
                continue
            if fields.get('deleted'):
                task.deleted_at = utc_now()
                updated += 1
                continue
            next_assignee_id = int(fields['assignee_id']) if fields.get('assignee_id') not in (None, '') else task.assignee_id
            next_co_executor_ids = _normalize_co_executor_ids(fields, [link.user_id for link in task.co_executor_links] or ([task.co_executor_id] if task.co_executor_id else []))
            next_client_id = int(fields['client_id']) if fields.get('client_id') not in (None, '') else task.client_id
            next_completion_date = _parse_iso_datetime(fields.get('completion_date')) if 'completion_date' in fields else task.completion_date
            next_deadline = _parse_iso_datetime(fields.get('deadline')) if 'deadline' in fields else task.deadline
            await _ensure_client_access(session, user, role_names, accessible_client_ids, next_client_id)
            await _ensure_assignees_valid_for_client(session, role_names, next_client_id, next_assignee_id, next_co_executor_ids)
            _validate_task_dates(next_completion_date, next_deadline)
            await _validate_contract_task_dates(session, next_client_id, fields.get('no_contract', task.no_contract), next_completion_date, next_deadline)
            for field, value in fields.items():
                if field == 'deleted':
                    continue
                if field in {'co_executor_id', 'co_executor_ids'}:
                    await _set_task_co_executors(session, task, next_co_executor_ids)
                    continue
                if field in {'completion_date', 'deadline'}:
                    setattr(task, field, _parse_iso_datetime(value) if value else None)
                elif field in {'assignee_id', 'co_executor_id', 'client_id'}:
                    setattr(task, field, int(value) if value not in (None, '') else None)
                else:
                    setattr(task, field, value)
            updated += 1
        await session.commit()
    return JSONResponse({'ok': True, 'count': updated})


@router.post('/{task_id}/restore')
async def restore_task(task_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if not t:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_editable_by_user(t, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        t.deleted_at = None
        await session.commit()
        await log_activity('task', task_id, 'restored', actor_user_id=user.id, summary=f'Задача #{task_id} восстановлена')
    return JSONResponse({'ok': True})


@router.get('/{task_id}')
async def get_task(task_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        t = await _load_task_for_response(session, task_id)
        if not t:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_visible_to_user(t, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
    return JSONResponse(_task_to_dict(t))


@router.get('/{task_id}/accesses')
async def get_task_accesses(task_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        task = await _load_task_for_response(session, task_id)
        if not task:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_visible_to_user(task, user, role_names, accessible_client_ids, permissions):
            raise HTTPException(status_code=403, detail='Forbidden')
        return JSONResponse(_client_accesses_for_task(task))


@router.get('/{task_id}/activity')
async def task_activity(task_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_visible_to_user(task, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
    logs = await list_activity(limit=100, entity_type='task', entity_id=task_id)
    return JSONResponse([{
        'id': log.id,
        'action': log.action,
        'field_name': log.field_name,
        'old_value': log.old_value,
        'new_value': log.new_value,
        'summary': log.summary,
        'actor': log.user.username if log.user else '',
        'created_at': format_datetime(log.created_at, settings.tz) if log.created_at else '',
    } for log in logs])


@router.post('')
async def create_task(data: dict, user=Depends(get_current_user)):
    async with async_session() as session:
        ts = TaskService(session)
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        client_id = data.get('client_id')
        assignee_id = data.get('assignee_id')
        co_executor_ids = _normalize_co_executor_ids(data)
        dl = _parse_iso_datetime(data.get('deadline'))
        cd = _parse_iso_datetime(data.get('completion_date'))
        await _ensure_client_access(session, user, role_names, accessible_client_ids, client_id)
        await _ensure_assignees_valid_for_client(session, role_names, client_id, assignee_id, co_executor_ids)
        _validate_task_dates(cd, dl)
        await _validate_contract_task_dates(session, client_id, data.get('no_contract', False), cd, dl)
        t = await ts.create_task(
            title=data['title'],
            client_id=client_id,
            task_type=data.get('task_type', 'custom'),
            deadline=dl,
            completion_date=cd,
            priority=data.get('priority', 'medium'),
            notes=data.get('notes'),
            comment=data.get('comment'),
            checklist=data.get('checklist'),
        )
        t.creator_id = user.id
        t.assignee_id = assignee_id
        await _set_task_co_executors(session, t, co_executor_ids)
        t.no_contract = data.get('no_contract', False)
        t.visibility = data.get('visibility', 'public')
        t.client_access_ids = json.dumps(data.get('client_access_ids', []), ensure_ascii=False)
        await _add_assignment_notifications(session, t, user.id, _assignment_user_ids(assignee_id, co_executor_ids))
        await session.commit()
        response_task = await _load_task_for_response(session, t.id)
        await log_activity('task', t.id, 'created', actor_user_id=user.id, summary=f'Создана задача: {t.title}')
    return JSONResponse(_task_to_dict(response_task or t), status_code=201)


@router.put('/{task_id}')
async def update_task(task_id: int, data: dict, user=Depends(get_current_user)):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if not t:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_editable_by_user(t, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        old_assignee_ids = _assignment_user_ids(
            t.assignee_id,
            [link.user_id for link in t.co_executor_links] or ([t.co_executor_id] if t.co_executor_id else []),
        )
        next_client_id = data['client_id'] if 'client_id' in data else t.client_id
        next_assignee_id = data['assignee_id'] if 'assignee_id' in data else t.assignee_id
        next_co_executor_ids = _normalize_co_executor_ids(data, [link.user_id for link in t.co_executor_links] or ([t.co_executor_id] if t.co_executor_id else []))
        next_deadline = _parse_iso_datetime(data.get('deadline')) if 'deadline' in data else t.deadline
        next_completion_date = _parse_iso_datetime(data.get('completion_date')) if 'completion_date' in data else t.completion_date
        changes = []

        def track(field, old, new):
            old_value = _activity_value(old)
            new_value = _activity_value(new)
            if old_value != new_value:
                changes.append((field, old_value, new_value))

        if data.get('title'):
            track('title', t.title, data['title'])
        if data.get('status'):
            track('status', t.status, data['status'])
        if data.get('priority'):
            track('priority', t.priority, data['priority'])
        if data.get('task_type'):
            track('task_type', t.task_type, data['task_type'])
        if 'client_id' in data:
            track('client_id', t.client_id, data['client_id'])
        if 'notes' in data:
            track('notes', t.notes, data['notes'])
        if 'comment' in data:
            track('comment', t.comment, data['comment'])
        if 'assignee_id' in data:
            track('assignee_id', t.assignee_id, data['assignee_id'])
        if 'co_executor_id' in data or 'co_executor_ids' in data:
            track('co_executor_ids', [link.user_id for link in t.co_executor_links], next_co_executor_ids)
        if 'deadline' in data:
            track('deadline', t.deadline, next_deadline)
        if 'completion_date' in data:
            track('completion_date', t.completion_date, next_completion_date)
        if 'no_contract' in data:
            track('no_contract', t.no_contract, data['no_contract'])
        if 'visibility' in data:
            track('visibility', t.visibility, data['visibility'])
        if 'client_access_ids' in data:
            track('client_access_ids', json.loads(t.client_access_ids) if isinstance(t.client_access_ids, str) and t.client_access_ids else [], data.get('client_access_ids') or [])
        if 'checklist' in data:
            track('checklist', t.checklist, data['checklist'])
        await _ensure_client_access(session, user, role_names, accessible_client_ids, next_client_id)
        await _ensure_assignees_valid_for_client(session, role_names, next_client_id, next_assignee_id, next_co_executor_ids)
        _validate_task_dates(next_completion_date, next_deadline)
        next_no_contract = data.get('no_contract', t.no_contract) if 'no_contract' in data else t.no_contract
        await _validate_contract_task_dates(session, next_client_id, next_no_contract, next_completion_date, next_deadline)
        if data.get('title'):
            t.title = data['title']
        if data.get('status'):
            t.status = data['status']
        if data.get('priority'):
            t.priority = data['priority']
        if data.get('task_type'):
            t.task_type = data['task_type']
        if 'client_id' in data:
            t.client_id = data['client_id']
        if 'notes' in data:
            t.notes = data['notes']
        if 'comment' in data:
            t.comment = data['comment']
        if 'assignee_id' in data:
            t.assignee_id = data['assignee_id']
        if 'co_executor_id' in data or 'co_executor_ids' in data:
            await _set_task_co_executors(session, t, next_co_executor_ids)
        if 'no_contract' in data:
            t.no_contract = data['no_contract']
        if 'visibility' in data:
            t.visibility = data['visibility']
        if 'client_access_ids' in data:
            t.client_access_ids = json.dumps(data.get('client_access_ids') or [], ensure_ascii=False)
        if data.get('deadline'):
            t.deadline = _parse_iso_datetime(data['deadline'])
        if 'deadline' in data and not data.get('deadline'):
            t.deadline = None
        if data.get('completion_date'):
            t.completion_date = _parse_iso_datetime(data['completion_date'])
        if 'completion_date' in data and not data.get('completion_date'):
            t.completion_date = None
        if 'checklist' in data:
            t.checklist = data['checklist']
        new_assignee_ids = _assignment_user_ids(t.assignee_id, next_co_executor_ids)
        await _add_assignment_notifications(session, t, user.id, new_assignee_ids - old_assignee_ids)
        await session.commit()
        if changes:
            for field, old_value, new_value in changes:
                label = TASK_FIELD_LABELS.get(field, field)
                await log_activity('task', task_id, 'field_changed', actor_user_id=user.id, field_name=label, old_value=old_value, new_value=new_value, summary=f'Задача #{task_id}: изменено поле «{label}»')
        else:
            await log_activity('task', task_id, 'updated', actor_user_id=user.id, summary=f'Задача #{task_id} обновлена')
    return JSONResponse({'ok': True})


@router.delete('/{task_id}')
async def delete_task(task_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if t:
            role_names = await get_user_role_names(user.id)
            accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
            if not task_is_editable_by_user(t, user, role_names, accessible_client_ids):
                raise HTTPException(status_code=403, detail='Forbidden')
            t.deleted_at = utc_now()
            await session.commit()
        await log_activity('task', task_id, 'deleted', actor_user_id=user.id, summary=f'Задача #{task_id} удалена')
    return JSONResponse({'ok': True})


@router.post('/{task_id}/move')
async def move_task(task_id: int, data: dict, user=Depends(get_current_user)):
    new_status = data.get('status')
    if new_status not in ('todo', 'in_progress', 'waiting', 'client_check', 'done', 'overdue'):
        raise HTTPException(status_code=400, detail='Invalid status')
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if not t:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_editable_by_user(t, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        old_status = t.status
        t.status = new_status
        await session.commit()
        await log_activity('task', task_id, 'status_changed', actor_user_id=user.id,
            field_name='status', old_value=old_status, new_value=new_status,
            summary=f'Задача #{task_id}: {old_status} → {new_status}')
    return JSONResponse({'ok': True})


@router.get('/{task_id}/comments')
async def list_comments(task_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_visible_to_user(task, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        r = await session.execute(
            select(TaskComment).where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at)
        )
        comments = r.scalars().all()
    return JSONResponse([{
        'id': c.id,
        'user_id': c.user_id,
        'content': c.content,
        'mentions': json.loads(c.mentions) if isinstance(c.mentions, str) else (c.mentions or []),
        'created_at': c.created_at.isoformat() if c.created_at else '',
    } for c in comments])


@router.post('/{task_id}/comments')
async def add_comment(task_id: int, data: dict, user=Depends(get_current_user)):
    content = data.get('content', '')
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail='Content is required')
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_visible_to_user(task, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        c = TaskComment(
            task_id=task_id,
            user_id=user.id,
            content=content.strip(),
            mentions=json.dumps(data.get('mentions', []), ensure_ascii=False),
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)
    return JSONResponse({'id': c.id, 'content': c.content, 'created_at': c.created_at.isoformat() if c.created_at else ''}, status_code=201)


@router.post('/{task_id}/upload')
async def upload_file(task_id: int, file: UploadFile, user=Depends(get_current_user)):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if not t:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_editable_by_user(t, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        data = await file.read()
        att = FileAttachment(
            task_id=task_id,
            filename=file.filename or 'file',
            original_name=file.filename or 'file',
            content_type=file.content_type or 'application/octet-stream',
            size=len(data),
            data=data,
        )
        session.add(att)
        await session.commit()
    return JSONResponse({'ok': True, 'id': att.id, 'name': att.original_name, 'size': att.size})


@router.get('/{task_id}/files')
async def list_files(task_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_visible_to_user(task, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        files = (await session.execute(
            select(FileAttachment).where(FileAttachment.task_id == task_id).order_by(FileAttachment.uploaded_at)
        )).scalars().all()
    return JSONResponse([
        {
            'id': f.id,
            'name': f.original_name,
            'size': f.size,
            'content_type': f.content_type,
            'uploaded_at': format_datetime(f.uploaded_at, settings.tz) if f.uploaded_at else '',
        }
        for f in files
    ])


@router.get('/{task_id}/files/{file_id}/download')
async def download_file(task_id: int, file_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_visible_to_user(task, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        att = await session.get(FileAttachment, file_id)
        if not att or att.task_id != task_id:
            raise HTTPException(status_code=404, detail='File not found')
        filename = (att.original_name or att.filename or 'file').replace('"', '')
        encoded_filename = quote(filename)
        disposition = 'inline' if (att.content_type or '').startswith(('image/', 'application/pdf')) else 'attachment'
        return Response(
            content=att.data,
            media_type=att.content_type or 'application/octet-stream',
            headers={'Content-Disposition': f'{disposition}; filename="file"; filename*=UTF-8\'\'{encoded_filename}'},
        )


@router.delete('/{task_id}/files/{file_id}')
async def delete_task_file(task_id: int, file_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_editable_by_user(task, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        att = await session.get(FileAttachment, file_id)
        if not att or att.task_id != task_id:
            raise HTTPException(status_code=404, detail='File not found')
        await session.delete(att)
        await session.commit()
    return JSONResponse({'ok': True})
