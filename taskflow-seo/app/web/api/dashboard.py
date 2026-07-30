from datetime import datetime, timedelta

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from app.core.cache import dashboard_cache
from app.core.config import settings
from app.core.database import async_session
from app.core.models import Client, ClientResponsible, Task, TaskCoExecutor, User
from app.core.permissions import client_is_visible_to_user, get_accessible_client_ids, get_current_user, get_user_permissions, get_user_role_names, task_co_executor_ids, task_is_visible_to_user, user_is_superadmin
from app.core.utils.timezone import safe_dt, to_utc, utc_now
from app.services.client_service import ClientService
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _task_visibility_condition(user_id: int, is_superadmin: bool):
    if is_superadmin:
        return None
    co_executor_exists = select(TaskCoExecutor.id).where(
        TaskCoExecutor.task_id == Task.id,
        TaskCoExecutor.user_id == user_id,
    ).exists()
    return or_(
        Task.creator_id == user_id,
        Task.assignee_id == user_id,
        Task.co_executor_id == user_id,
        co_executor_exists,
    )


@router.get('/stats')
async def dashboard_stats(user=Depends(get_current_user)):
    cache_key = ('stats', user.id)
    if cached := dashboard_cache.get(cache_key):
        return JSONResponse(cached)
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        tz = settings.tz
        now_local = datetime.now(tz)
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = to_utc(today_start)
        conditions = [Task.deleted_at.is_(None)]
        visibility = _task_visibility_condition(user.id, user_is_superadmin(role_names))
        if visibility is not None:
            conditions.append(visibility)
        task_counts = (await session.execute(select(
            func.count(Task.id),
            func.count(Task.id).filter(Task.status == 'done'),
            func.count(Task.id).filter(Task.status == 'in_progress'),
            func.count(Task.id).filter(
                Task.status != 'done',
                func.coalesce(Task.completion_date, Task.deadline) < today_start_utc,
            ),
        ).where(*conditions))).one()
        total, done, in_progress, overdue = (int(value or 0) for value in task_counts)
        active_clients = int((await session.execute(select(func.count(Client.id)).where(
            Client.deleted_at.is_(None), Client.status == 'active',
        ))).scalar_one() or 0)
        ending_clients = int((await session.execute(select(func.count(Client.id)).where(
            Client.deleted_at.is_(None),
            Client.contract_end >= utc_now(),
            Client.contract_end <= utc_now() + timedelta(days=14),
        ))).scalar_one() or 0)

    payload = {
        'total': total,
        'done': done,
        'in_progress': in_progress,
        'overdue': overdue,
        'active_clients': active_clients,
        'ending_clients': ending_clients,
    }
    dashboard_cache.set(cache_key, payload)
    return JSONResponse(payload)


@router.get('/chart')
async def dashboard_chart(period: str = Query('month'), user=Depends(get_current_user)):
    cache_key = ('chart', user.id, period)
    if cached := dashboard_cache.get(cache_key):
        return JSONResponse(cached)
    tz = settings.tz
    now_local = datetime.now(tz)

    if period == 'week':
        start = now_local - timedelta(days=6)
        days = 7
    elif period == 'quarter':
        start = now_local - timedelta(days=89)
        days = 90
    elif period == 'year':
        start = now_local - timedelta(days=364)
        days = 365
    else:
        start = now_local - timedelta(days=29)
        days = 30

    start_day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        conditions = [Task.deleted_at.is_(None)]
        visibility = _task_visibility_condition(user.id, user_is_superadmin(role_names))
        if visibility is not None:
            conditions.append(visibility)
        created_day = func.date(func.timezone(str(tz), Task.created_at))
        done_day = func.date(func.timezone(str(tz), Task.updated_at))
        created_rows = (await session.execute(select(created_day, func.count(Task.id)).where(
            *conditions, Task.created_at >= to_utc(start_day),
        ).group_by(created_day))).all()
        done_rows = (await session.execute(select(done_day, func.count(Task.id)).where(
            *conditions, Task.status == 'done', Task.updated_at >= to_utc(start_day),
        ).group_by(done_day))).all()
    created_by_day = {day: int(count) for day, count in created_rows if day}
    done_by_day = {day: int(count) for day, count in done_rows if day}
    labels, created_data, done_data = [], [], []
    for i in range(days - 1, -1, -1):
        day = now_local - timedelta(days=i)
        labels.append(day.strftime('%d.%m'))
        created_data.append(created_by_day.get(day.date(), 0))
        done_data.append(done_by_day.get(day.date(), 0))

    payload = {'labels': labels, 'created': created_data, 'done': done_data}
    dashboard_cache.set(cache_key, payload)
    return JSONResponse(payload)


@router.get('/focus')
async def dashboard_focus(limit: int = Query(7, ge=1, le=20), user=Depends(get_current_user)):
    cache_key = ('focus', user.id, limit)
    if cached := dashboard_cache.get(cache_key):
        return JSONResponse(cached)
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        conditions = [Task.deleted_at.is_(None), Task.status != 'done']
        visibility = _task_visibility_condition(user.id, user_is_superadmin(role_names))
        if visibility is not None:
            conditions.append(visibility)
        tasks = (await session.execute(select(
            Task.id, Task.title, Task.status, Task.completion_date, Task.deadline,
            Client.org_name.label('client'),
        ).outerjoin(Client, Client.id == Task.client_id).where(*conditions).order_by(
            func.coalesce(Task.completion_date, Task.deadline).asc().nulls_last(),
            Task.id.desc(),
        ).limit(limit))).all()
        payload = [{
            'id': task.id,
            'title': task.title,
            'status': task.status,
            'client': task.client or '',
            'completion_date': task.completion_date.isoformat() if task.completion_date else None,
            'deadline': task.deadline.isoformat() if task.deadline else None,
        } for task in tasks[:limit]]
        dashboard_cache.set(cache_key, payload)
        return JSONResponse(payload)


@router.get('/client-table')
async def client_table(user=Depends(get_current_user)):
    async with async_session() as session:
        cs = ClientService(session)
        clients = await cs.list_clients()
        task_rows = (await session.execute(select(
            Task.id, Task.client_id, Task.title, Task.status, Task.completion_date, Task.deadline,
            Task.created_at, Task.updated_at, Task.creator_id, Task.assignee_id,
        ).where(Task.deleted_at.is_(None)))).all()
        co_executor_rows = (await session.execute(select(TaskCoExecutor.task_id, TaskCoExecutor.user_id))).all()
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
    co_executor_by_task = {}
    for task_id, co_executor_id in co_executor_rows:
        co_executor_by_task.setdefault(task_id, set()).add(co_executor_id)
    visible_tasks = [
        t for t in task_rows
        if user_is_superadmin(role_names)
        or user.id in {t.creator_id, t.assignee_id} | co_executor_by_task.get(t.id, set())
    ]
    result = []
    for client in [c for c in clients if client_is_visible_to_user(c.id, role_names, accessible_client_ids)]:
        client_tasks = [task for task in visible_tasks if task.client_id == client.id]
        total = len([task for task in client_tasks if task.status != 'done'])
        done_c = len([task for task in client_tasks if task.status == 'done'])
        if total or done_c:
            result.append({'id': client.id, 'name': client.org_name, 'total': total, 'done': done_c, 'status': client.status})
    result.sort(key=lambda item: item['total'], reverse=True)
    result = result[:10]
    return JSONResponse(result)


@router.get('/organizations')
async def organization_overview(
    scope: str = Query('mine'),
    user_id: int | None = Query(None),
    user=Depends(get_current_user),
):
    cache_key = ('organizations', user.id, scope, user_id)
    if cached := dashboard_cache.get(cache_key):
        return JSONResponse(cached)
    async with async_session() as session:
        clients = await ClientService(session).list_clients()
        task_rows = (await session.execute(select(
            Task.id, Task.client_id, Task.title, Task.status, Task.completion_date, Task.deadline,
            Task.created_at, Task.updated_at, Task.creator_id, Task.assignee_id,
        ).where(Task.deleted_at.is_(None)))).all()
        co_executor_rows = (await session.execute(select(TaskCoExecutor.task_id, TaskCoExecutor.user_id))).all()
        role_names = await get_user_role_names(user.id)
        permissions = await get_user_permissions(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
        can_view_team = user_is_superadmin(role_names) or permissions.get('all') or permissions.get('dashboard_team')
        if (scope == 'all' or user_id is not None) and not can_view_team:
            raise HTTPException(status_code=403, detail='Нет доступа к сводке команды')

        users = (await session.execute(select(User).order_by(User.username))).scalars().all()
        responsible_rows = (await session.execute(select(ClientResponsible))).scalars().all()

    target_user_id = user_id if user_id is not None else user.id
    co_executor_by_task: dict[int, set[int]] = {}
    for task_id, co_executor_id in co_executor_rows:
        co_executor_by_task.setdefault(task_id, set()).add(co_executor_id)
    responsible_by_client: dict[int, set[int]] = {}
    for row in responsible_rows:
        responsible_by_client.setdefault(row.client_id, set()).add(row.user_id)

    full_team_scope = can_view_team and (scope == 'all' or user_id is not None)
    if full_team_scope:
        visible_tasks = task_rows
    else:
        visible_tasks = [row for row in task_rows if target_user_id in ({row.creator_id, row.assignee_id} | co_executor_by_task.get(row.id, set()))]

    tasks_by_client: dict[int, list] = {}
    for task in visible_tasks:
        if task.client_id is not None:
            tasks_by_client.setdefault(task.client_id, []).append(task)

    usernames = {item.id: item.username for item in users}
    now = datetime.now(settings.tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)
    result = []

    def task_date(task):
        raw = task.completion_date or task.deadline
        return safe_dt(raw).astimezone(settings.tz) if raw else None

    for client in clients:
        if not client_is_visible_to_user(client.id, role_names, accessible_client_ids):
            continue
        responsible_ids = responsible_by_client.get(client.id, set())
        client_tasks = tasks_by_client.get(client.id, [])
        if target_user_id in responsible_ids and not full_team_scope:
            client_tasks = [row for row in task_rows if row.client_id == client.id]
        is_mine = target_user_id in responsible_ids or bool(client_tasks)
        if scope != 'all' and not is_mine:
            continue

        active_tasks = [task for task in client_tasks if task.status != 'done']
        overdue = [task for task in active_tasks if task.status == 'overdue' or (task_date(task) and task_date(task) < today_start)]
        due_soon = [task for task in active_tasks if task_date(task) and today_start <= task_date(task) < today_start + timedelta(days=8)]
        done_this_month = [
            task for task in client_tasks
            if task.status == 'done' and task.updated_at and safe_dt(task.updated_at).astimezone(settings.tz) >= month_start
        ]
        dated_active = [task for task in active_tasks if task_date(task)]
        nearest = min(dated_active, key=task_date) if dated_active else None
        activity_dates = [safe_dt(task.updated_at or task.created_at).astimezone(settings.tz) for task in client_tasks if task.updated_at or task.created_at]
        if client.created_at:
            activity_dates.append(safe_dt(client.created_at).astimezone(settings.tz))
        last_activity = max(activity_dates) if activity_dates else None
        inactive_days = max(0, (today_start.date() - last_activity.date()).days) if last_activity else None
        participant_ids = set(responsible_ids)
        for task in client_tasks:
            participant_ids.update(item for item in {task.creator_id, task.assignee_id} | co_executor_by_task.get(task.id, set()) if item)

        result.append({
            'id': client.id,
            'name': client.org_name,
            'domain': client.domain or '',
            'status': client.status,
            'active': len(active_tasks),
            'overdue': len(overdue),
            'due_soon': len(due_soon),
            'done_this_month': len(done_this_month),
            'last_activity': last_activity.isoformat() if last_activity else None,
            'inactive_days': inactive_days,
            'is_stale': inactive_days is None or inactive_days >= 14,
            'needs_attention': bool(overdue) or inactive_days is None or inactive_days >= 14 or not responsible_ids,
            'nearest_task': ({
                'id': nearest.id,
                'title': nearest.title,
                'date': task_date(nearest).isoformat(),
            } if nearest else None),
            'responsible_user_ids': sorted(responsible_ids),
            'responsible_users': [usernames[item] for item in sorted(responsible_ids) if item in usernames],
            'participants': [usernames[item] for item in sorted(participant_ids) if item in usernames],
        })

    result.sort(key=lambda item: (not item['needs_attention'], -item['overdue'], -item['active'], item['name'].lower()))
    payload = {
        'items': result,
        'scope': scope,
        'selected_user_id': target_user_id,
        'can_view_team': bool(can_view_team),
        'users': [{'id': item.id, 'username': item.username} for item in users] if can_view_team else [],
    }
    dashboard_cache.set(cache_key, payload)
    return JSONResponse(payload)


@router.get('/client-summaries')
async def client_work_summaries(user=Depends(get_current_user)):
    cache_key = ('client-summaries', user.id)
    if cached := dashboard_cache.get(cache_key):
        return JSONResponse(cached)
    async with async_session() as session:
        role_names = await get_user_role_names(user.id)
        conditions = [Task.deleted_at.is_(None)]
        visibility = _task_visibility_condition(user.id, user_is_superadmin(role_names))
        if visibility is not None:
            conditions.append(visibility)
        task_date = func.coalesce(Task.completion_date, Task.deadline)
        today_start = to_utc(datetime.now(settings.tz).replace(hour=0, minute=0, second=0, microsecond=0))
        rows = (await session.execute(select(
            Task.client_id,
            func.count(Task.id).label('total'),
            func.count(Task.id).filter(Task.status != 'done').label('active'),
            func.count(Task.id).filter(Task.status != 'done', task_date < today_start).label('overdue'),
            func.max(func.coalesce(Task.updated_at, Task.created_at)).label('last_activity'),
        ).where(*conditions, Task.client_id.is_not(None)).group_by(Task.client_id))).all()
    payload = [{
        'client_id': row.client_id,
        'total': int(row.total or 0),
        'active': int(row.active or 0),
        'overdue': int(row.overdue or 0),
        'last_activity': row.last_activity.isoformat() if row.last_activity else None,
    } for row in rows]
    dashboard_cache.set(cache_key, payload)
    return JSONResponse(payload)


@router.get('/expiring')
async def expiring_contracts(user=Depends(get_current_user)):
    async with async_session() as session:
        cs = ClientService(session)
        clients = await cs.get_clients_ending_soon(days=14)
        role_names = await get_user_role_names(user.id)
        accessible_client_ids = await get_accessible_client_ids(session, user.id, role_names)
    return JSONResponse([{
        'id': c.id,
        'org_name': c.org_name,
        'contract_end': c.contract_end.isoformat() if c.contract_end else '',
        'status': c.status,
    } for c in clients if client_is_visible_to_user(c.id, role_names, accessible_client_ids)])
