from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import async_session
from app.core.models import Client, Task, TaskCoExecutor
from app.core.permissions import get_accessible_client_ids, get_current_user, get_user_permissions, get_user_role_names, task_is_editable_by_user, task_is_visible_to_user, user_is_superadmin
from app.core.utils.timezone import safe_dt, to_utc

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


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


@router.get('')
async def calendar_events(
    start: str = Query(''),
    end: str = Query(''),
    assignee: int = Query(None),
    scope: str = Query('mine'),
    scope_user_id: str = Query(None),
    user=Depends(get_current_user),
):
    tz = settings.tz
    async with async_session() as session:
        query = (
            select(Task)
            .options(selectinload(Task.co_executor_links))
            .where(Task.deleted_at.is_(None), Task.status != 'done')
        )
        if start and end:
            try:
                range_start = datetime.fromisoformat(start).replace(tzinfo=tz)
                range_end = datetime.fromisoformat(end).replace(tzinfo=tz) + timedelta(days=1)
                query = query.where(
                    Task.completion_date >= to_utc(range_start),
                    Task.completion_date < to_utc(range_end),
                )
            except (ValueError, TypeError):
                pass
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        scope_condition = _task_scope_condition(scope, user.id, role_names, permissions, scope_user_id)
        if scope_condition is not None:
            query = query.where(scope_condition)
        if assignee:
            query = query.where(Task.assignee_id == assignee)
        r = await session.execute(
            query.order_by(Task.completion_date.asc(), Task.id.asc())
        )
        tasks = r.scalars().all()

    events = []
    for t in tasks:
        if not task_is_visible_to_user(t, user, role_names, accessible_client_ids, permissions):
            continue
        if assignee and t.assignee_id != assignee:
            continue
        cal_date = t.completion_date
        if not cal_date:
            continue
        cd = safe_dt(cal_date).astimezone(tz)
        if cd is None:
            continue
        day_start = cd.replace(hour=0, minute=0, second=0, microsecond=0)
        if start and end:
            try:
                s = datetime.fromisoformat(start)
                e = datetime.fromisoformat(end)
                if s.tzinfo is None:
                    s = s.replace(tzinfo=tz)
                if e.tzinfo is None:
                    e = e.replace(tzinfo=tz)
                if day_start < s or day_start > e:
                    continue
            except (ValueError, TypeError):
                pass

        days_until = (day_start - datetime.now(tz)).days
        if t.status == 'done':
            color = '#6c757d'
        elif t.status == 'overdue' or days_until < 0:
            color = '#dc3545'
        elif days_until <= 2:
            color = '#ffc107'
        else:
            color = '#198754'

        start_str = cd.strftime('%Y-%m-%dT%H:%M:%S')
        events.append({
            'id': str(t.id),
            'title': t.title,
            'start': start_str,
            'date': cd.strftime('%Y-%m-%d'),
            'allDay': True,
            'color': color,
            'textColor': '#000' if color == '#ffc107' else '#fff',
            'status': t.status,
            'priority': t.priority,
            'task_type': t.task_type,
            'creator_id': t.creator_id,
            'assignee_id': t.assignee_id,
            'co_executor_id': t.co_executor_id,
            'co_executor_ids': [link.user_id for link in getattr(t, 'co_executor_links', []) or [] if link.user_id],
        })

    return JSONResponse(events)


@router.patch('/{task_id}')
async def update_calendar_event(task_id: int, data: dict, user=Depends(get_current_user)):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if not t:
            raise HTTPException(status_code=404, detail='Task not found')
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        if not task_is_editable_by_user(t, user, role_names, accessible_client_ids):
            raise HTTPException(status_code=403, detail='Forbidden')
        if data.get('deadline'):
            dl = datetime.fromisoformat(data['deadline'])
            t.deadline = to_utc(dl)
        if data.get('completion_date'):
            cd = datetime.fromisoformat(data['completion_date'])
            t.completion_date = to_utc(cd)
        if t.completion_date and t.deadline and t.completion_date > t.deadline:
            raise HTTPException(status_code=400, detail='Дата выполнения не может быть позже крайнего срока')
        if t.client_id and not t.no_contract and t.completion_date:
            client = await session.get(Client, t.client_id)
            contract_end = safe_dt(client.contract_end) if client and client.contract_end else None
            completion_date = safe_dt(t.completion_date)
            if contract_end and completion_date and contract_end < completion_date:
                raise HTTPException(status_code=400, detail='Дата выполнения не может быть позже окончания договора клиента')
        await session.commit()
    return JSONResponse({'ok': True})
