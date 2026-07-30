from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.auth import COOKIE_NAME, make_session_token, verify_session_token
from app.core.config import settings
from app.core.database import async_session
from app.core.models import Client, FileAttachment, Reminder, Task, User, UserSettings
from app.core.utils.timezone import format_datetime, to_utc, utc_now
from app.services.activity_service import list_activity, log_activity
from app.services.client_service import ClientService
from app.services.notification_service import NotificationService
from app.services.tag_service import TagService
from app.services.task_service import TaskService
from app.services.user_service import authenticate, get_user
from app.web.templates_setup import templates

router = APIRouter()


async def current_user(request: Request) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = verify_session_token(token)
    if user_id is None:
        return None
    return await get_user(user_id)


async def require_user(request: Request) -> User | None:
    return await current_user(request)

CHECKLIST_TEMPLATES = {
    'article': [
        {'text': 'Статья 1', 'done': False},
        {'text': 'Статья 2', 'done': False},
        {'text': 'Статья 3', 'done': False},
    ],
    'seo': [
        {'text': 'Сбор семантики', 'done': False},
        {'text': 'Аудит', 'done': False},
        {'text': 'Оптимизация', 'done': False},
        {'text': 'Отчёт', 'done': False},
    ],
    'dev': [
        {'text': 'ТЗ', 'done': False},
        {'text': 'Реализация', 'done': False},
        {'text': 'Тест', 'done': False},
        {'text': 'Деплой', 'done': False},
    ],
}


async def require_auth(request: Request) -> User | None:
    return await current_user(request)


def safe_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo('UTC'))
    return dt


def to_tz(dt: datetime | None) -> datetime | None:
    dt = safe_dt(dt)
    if dt is None:
        return None
    return dt.astimezone(settings.tz)


def ctx(request: Request, user=None, **kw) -> dict:
    tz = settings.tz
    base = {
        'request': request,
        'now': datetime.now(tz),
        'tz': tz,
        'to_tz': to_tz,
        'format_dt': format_datetime,
        'user': user,
    }
    base.update(kw)
    return base


async def _user_ctx(request: Request, **kw) -> dict:
    u = await current_user(request)
    return ctx(request, user=u, **kw)





def parse_web_deadline(text: str) -> datetime | None:
    if not text or not text.strip():
        return None
    from app.core.utils.timezone import parse_deadline
    return parse_deadline(text.strip(), settings.tz)


# ─── Auth ─────────────────────────────────────────────────────

@router.get('/login')
async def login_page(request: Request):
    u = await current_user(request)
    if u:
        return RedirectResponse(url='/', status_code=302)
    return templates.TemplateResponse(request, 'login.html', ctx(request))


@router.post('/login')
async def login_post(request: Request, username: str = Form(''), password: str = Form('')):
    u = await authenticate(username, password)
    if u:
        resp = RedirectResponse(url='/', status_code=302)
        resp.set_cookie(key=COOKIE_NAME, value=make_session_token(u.id), httponly=True, max_age=86400 * 30)
        return resp
    return templates.TemplateResponse(request, 'login.html', ctx(request, error='Неверное имя или пароль'))


@router.get('/logout')
async def logout():
    resp = RedirectResponse(url='/login', status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ─── Dashboard ────────────────────────────────────────────────

@router.get('/', summary='Dashboard', description='Главная панель со статистикой')
async def dashboard(request: Request):
    user = await current_user(request)
    if not user:
        return RedirectResponse(url='/login')
    period = request.query_params.get('period', 'month')
    async with async_session() as session:
        ts = TaskService(session)
        cs = ClientService(session)
        tz = settings.tz
        now_local = datetime.now(tz)
        tasks_all = await ts.list_tasks()

        # Релевантная дата задачи — как в календаре: completion_date ?? deadline
        def task_date(t: Task) -> datetime | None:
            raw = t.completion_date or t.deadline
            return safe_dt(raw) if raw else None

        # Границы сегодняшнего дня
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        today_start_utc = to_utc(today_start)
        today_end_utc = to_utc(today_end)

        # Просроченные: дата задачи раньше сегодняшнего дня и не выполнено
        overdue = [
            t for t in tasks_all
            if task_date(t) and task_date(t) < today_start_utc and t.status != 'done'
        ]

        # Сегодня: дата задачи в пределах сегодняшнего дня
        due_today = [
            t for t in tasks_all
            if task_date(t) and today_start_utc <= task_date(t) < today_end_utc
            and t.status != 'done'
        ]

        # Fallback: если нет просроченных/сегодня — показываем ближайшие активные
        active_tasks = [t for t in tasks_all if t.status not in ('done',)]
        active_sorted = sorted(active_tasks, key=lambda t: (
            0 if task_date(t) is None else 1,
            task_date(t) if task_date(t) else datetime.max.replace(tzinfo=ZoneInfo('UTC'))
        ))
        fallback_tasks = active_sorted[:5]

        has_overdue = bool(overdue)
        has_today = bool(due_today)
        overdue_display = overdue[:5] if has_overdue else fallback_tasks
        today_display = due_today[:5] if has_today else fallback_tasks

        done = [t for t in tasks_all if t.status == 'done']
        clients = await cs.list_clients()
        active_clients = [c for c in clients if c.status == 'active']
        ending_soon = await cs.get_clients_ending_soon(days=14)

        # Период для графиков
        if period == 'week':
            start_date = now_local - timedelta(days=6)
        elif period == 'month':
            start_date = now_local - timedelta(days=29)
        elif period == 'quarter':
            start_date = now_local - timedelta(days=89)
        elif period == 'year':
            start_date = now_local - timedelta(days=364)
        else:
            start_date = datetime(1970, 1, 1, tzinfo=tz)

        period_length = (now_local - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=period_length - 1)

        def count_done_in_period(start_dt, end_dt):
            cnt = 0
            for t in tasks_all:
                if t.status == 'done' and t.updated_at:
                    upd = safe_dt(t.updated_at).astimezone(tz)
                    if start_dt <= upd <= end_dt:
                        cnt += 1
            return cnt

        done_current = count_done_in_period(start_date, now_local)
        done_previous = count_done_in_period(prev_start, prev_end) if period != 'all' else 0
        diff = done_current - done_previous
        pct = (diff / done_previous * 100) if done_previous != 0 else (0 if done_current == 0 else 100)

        # Статусы
        status_counts = {'todo': 0, 'in_progress': 0, 'done': 0, 'overdue': 0}
        for t in tasks_all:
            is_overdue = bool(
                task_date(t) and task_date(t) < today_start_utc and t.status not in ('done', 'overdue')
            )
            key = 'overdue' if is_overdue else t.status
            status_counts[key] = status_counts.get(key, 0) + 1

        # График активности за 14 дней
        chart_days = 14
        days_labels = []
        days_created = []
        days_done = []
        for i in range(chart_days - 1, -1, -1):
            day = now_local - timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            days_labels.append(day.strftime('%d.%m'))
            created_count = 0
            done_count = 0
            for t in tasks_all:
                if t.created_at and day_start <= safe_dt(t.created_at).astimezone(tz) < day_end:
                    created_count += 1
                if t.status == 'done' and t.updated_at and day_start <= safe_dt(t.updated_at).astimezone(tz) < day_end:
                    done_count += 1
            days_created.append(created_count)
            days_done.append(done_count)

        # Топ клиентов
        client_task_counts = []
        for c in sorted(clients, key=lambda x: len(x.tasks), reverse=True)[:10]:
            total = len([t for t in c.tasks if t.status != 'done'])
            done_c = len([t for t in c.tasks if t.status == 'done'])
            client_task_counts.append({'name': c.org_name[:15], 'total': total, 'done': done_c})

    period_labels = {'week': 'неделю', 'month': 'месяц', 'quarter': 'квартал', 'year': 'год', 'all': 'всё время'}

    return templates.TemplateResponse(request, 'dashboard.html', ctx(request, user=user,
        overdue_count=len(overdue),
        today_count=len(due_today),
        total_tasks=len(tasks_all),
        done_tasks=len(done),
        active_clients=len(active_clients),
        ending_clients=len(ending_soon),
        overdue_tasks=overdue_display,
        has_overdue=has_overdue,
        today_tasks=today_display,
        has_today=has_today,
        ending_clients_list=ending_soon[:5],
        status_chart=status_counts,
        chart_labels=days_labels,
        chart_created=days_created,
        chart_done=days_done,
        client_chart=client_task_counts,
        period=period,
        period_label=period_labels.get(period, period),
        done_current=done_current,
        done_previous=done_previous,
        done_diff=diff,
        done_pct=pct,
        page='dashboard',
    ))


# ─── Reports ──────────────────────────────────────────────────

@router.get('/reports', summary='Отчёты', description='Страница аналитики и отчётов')
async def reports_page(request: Request):
    user = await current_user(request)
    if not user:
        return RedirectResponse(url='/login')
    period = request.query_params.get('period', '12')
    months = int(period) if period.isdigit() else 12
    return templates.TemplateResponse(request, 'reports.html', ctx(request, user=user, page='reports', months=months))


@router.get('/api/reports/data')
async def api_reports_data(months: int = 12):
    async with async_session() as session:
        ts = TaskService(session)
        tasks_all = await ts.list_tasks()
        cs = ClientService(session)
        clients = await cs.list_clients()
    tz = settings.tz
    now_local = datetime.now(tz)

    # Monthly aggregation
    monthly = {}
    for i in range(months - 1, -1, -1):
        m = now_local.month - i
        y = now_local.year
        while m < 1:
            m += 12
            y -= 1
        key = f'{y}-{m:02d}'
        monthly[key] = {'created': 0, 'done': 0, 'overdue': 0}

    for t in tasks_all:
        if t.created_at:
            dt = safe_dt(t.created_at).astimezone(tz)
            key = dt.strftime('%Y-%m')
            if key in monthly:
                monthly[key]['created'] += 1
        if t.status == 'done' and t.updated_at:
            dt = safe_dt(t.updated_at).astimezone(tz)
            key = dt.strftime('%Y-%m')
            if key in monthly:
                monthly[key]['done'] += 1
        if t.status == 'overdue':
            dt = safe_dt(t.deadline or t.updated_at or t.created_at).astimezone(tz)
            key = dt.strftime('%Y-%m')
            if key in monthly:
                monthly[key]['overdue'] += 1

    # Status distribution
    status_dist = {'todo': 0, 'in_progress': 0, 'done': 0, 'overdue': 0}
    for t in tasks_all:
        s = t.status if t.status in status_dist else 'other'
        if s in status_dist:
            status_dist[s] += 1

    # Client funnel
    total_clients = len(clients)
    active_clients = sum(1 for c in clients if c.status == 'active')
    paused_clients = sum(1 for c in clients if c.status == 'paused')
    closed_clients = sum(1 for c in clients if c.status == 'closed')

    # Client task distribution
    client_tasks = []
    for c in sorted(clients, key=lambda x: len([t for t in x.tasks if t.status != 'done']), reverse=True)[:10]:
        total = len(c.tasks)
        done = sum(1 for t in c.tasks if t.status == 'done')
        active = total - done
        client_tasks.append({'name': c.org_name[:20], 'active': active, 'done': done})

    return JSONResponse({
        'labels': list(monthly.keys()),
        'created': [v['created'] for v in monthly.values()],
        'done': [v['done'] for v in monthly.values()],
        'overdue': [v['overdue'] for v in monthly.values()],
        'status_dist': status_dist,
        'client_funnel': {'total': total_clients, 'active': active_clients, 'paused': paused_clients, 'closed': closed_clients},
        'client_tasks': client_tasks,
    })


# ─── Tasks ────────────────────────────────────────────────────

@router.get('/tasks', summary='Список задач', description='Страница со списком всех задач с фильтрацией и пагинацией')
async def tasks_page(
    request: Request,
    client_id: int | None = Query(None),
    page: int = Query(1, ge=1),
):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        cs = ClientService(session)
        user = await current_user(request)
        all_clients = await cs.list_clients()
        clients_list = [{'id': c.id, 'name': c.org_name, 'end': format_datetime(c.contract_end, settings.tz) if c.contract_end else ''} for c in all_clients]

    return templates.TemplateResponse(request, 'tasks.html', ctx(request, user=user,
        page='tasks',
        all_clients=clients_list,
        checklist_templates_json=json.dumps(CHECKLIST_TEMPLATES, ensure_ascii=False),
    ))


@router.post('/tasks/create')
async def task_create(
    request: Request,
    title: str = Form(...),
    client_id: int | None = Form(None),
    deadline: str | None = Form(None),
    completion_date: str | None = Form(None),
    task_type: str = Form('custom'),
    priority: str = Form('medium'),
    notes: str | None = Form(None),
    comment: str | None = Form(None),
    checklist_raw: str | None = Form(None),
    recurring_interval: str | None = Form(None),
    recurring_count: int | None = Form(None),
):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    try:
        errors = []
        if not title or not title.strip():
            errors.append('Название задачи не может быть пустым')
        dl = None
        if deadline:
            dl = parse_web_deadline(deadline)
            if not dl:
                errors.append(f'Не удалось распознать дату: {deadline}')
        cd = None
        if completion_date:
            cd = parse_web_deadline(completion_date)
            if not cd:
                errors.append(f'Не удалось распознать дату выполнения: {completion_date}')
        if errors:
            return RedirectResponse(url='/tasks?error=' + '; '.join(errors), status_code=302)

        import contextlib
        checklist = None
        if checklist_raw and checklist_raw.strip():
            with contextlib.suppress(json.JSONDecodeError):
                checklist = json.loads(checklist_raw)

        async with async_session() as session:
            ts = TaskService(session)
            await ts.create_task(
                title=title.strip(),
                client_id=client_id if client_id else None,
                task_type=task_type,
                deadline=dl,
                completion_date=to_utc(cd) if cd else None,
                priority=priority,
                notes=notes,
                comment=comment,
                checklist=checklist,
            )
            # recurring поля
            from sqlalchemy import select as sa_select
            last = (await session.execute(sa_select(Task).order_by(Task.id.desc()).limit(1))).scalar()
            new_id = last.id if last else None
            if last and recurring_interval:
                last.recurring_interval = recurring_interval
                last.recurring_count = recurring_count or 999
                last.recurring_remaining = (recurring_count or 999)
                await session.commit()
        await log_activity('task', new_id, 'created', summary=f'Создана задача: {title.strip()}')
        return RedirectResponse(url='/tasks?success=Задача создана', status_code=302)
    except Exception as e:
        return RedirectResponse(url=f'/tasks?error=Ошибка: {e}', status_code=302)


@router.post('/tasks/{task_id}/edit')
async def task_edit(
    request: Request,
    task_id: int,
    title: str = Form(...),
    client_id: int | None = Form(None),
    deadline: str | None = Form(None),
    completion_date: str | None = Form(None),
    task_type: str = Form('custom'),
    priority: str = Form('medium'),
    notes: str | None = Form(None),
    comment: str | None = Form(None),
    status: str = Form('todo'),
    checklist_raw: str | None = Form(None),
):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    try:
        dl = None
        if deadline:
            dl = parse_web_deadline(deadline)
        cd = None
        if completion_date:
            cd = parse_web_deadline(completion_date)
        import contextlib
        checklist = None
        if checklist_raw and checklist_raw.strip():
            with contextlib.suppress(json.JSONDecodeError):
                checklist = json.loads(checklist_raw)

        async with async_session() as session:
            task = await session.get(Task, task_id)
            if task:
                changes = []
                if task.title != title.strip():
                    changes.append(f'название: "{task.title}" → "{title.strip()}"')
                task.title = title.strip()
                task.client_id = client_id if client_id else None
                task.deadline = to_utc(dl) if dl else None
                task.completion_date = to_utc(cd) if cd else None
                if task.task_type != task_type:
                    changes.append('тип')
                task.task_type = task_type
                if task.priority != priority:
                    changes.append('важность')
                task.priority = priority
                task.notes = notes
                task.comment = comment
                if task.status != status:
                    changes.append(f'статус: {task.status} → {status}')
                task.status = status
                if checklist is not None:
                    task.checklist = checklist
                    changes.append('чек-лист')
                await session.commit()
                if changes:
                    await log_activity('task', task_id, 'updated', summary=f'Задача #{task_id}: {"; ".join(changes[:3])}')
        return RedirectResponse(url=f'/tasks?success=Задача #{task_id} сохранена', status_code=302)
    except Exception as e:
        return RedirectResponse(url=f'/tasks?error=Ошибка: {e}', status_code=302)


@router.post('/tasks/{task_id}/done')
async def task_done(request: Request, task_id: int):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return RedirectResponse(url='/tasks?error=Задача не найдена')
        task.status = 'done'
        task.updated_at = utc_now()
        # Auto-generate next recurring task
        new_id = None
        if task.recurring_interval and (task.recurring_remaining is None or task.recurring_remaining > 0):
            next_dl = _next_recurring_date(safe_dt(task.deadline) if task.deadline else utc_now(), task.recurring_interval)
            next_cd = _next_recurring_date(safe_dt(task.completion_date) if task.completion_date else utc_now(), task.recurring_interval) if task.completion_date else None
            nt = Task(
                client_id=task.client_id,
                title=task.title,
                task_type=task.task_type,
                notes=task.notes,
                comment=task.comment,
                deadline=next_dl,
                completion_date=next_cd,
                status='todo', priority=task.priority,
                checklist=task.checklist,
                recurring_interval=task.recurring_interval,
                recurring_count=task.recurring_count,
                recurring_remaining=(task.recurring_remaining - 1) if task.recurring_remaining is not None else None,
                recurring_parent_id=task.recurring_parent_id or task.id,
            )
            session.add(nt)
            if task.recurring_remaining is not None:
                task.recurring_remaining -= 1
                if task.recurring_remaining <= 0:
                    task.recurring_interval = None
            await session.commit()
            await session.refresh(nt)
            new_id = nt.id
        else:
            await session.commit()
        await log_activity('task', task_id, 'done', summary=f'Задача #{task_id} выполнена')
    if new_id:
        return RedirectResponse(url='/tasks?success=Задача выполнена. Создана следующая повторяющаяся задача #' + str(new_id), status_code=302)
    return RedirectResponse(url='/tasks?success=Задача выполнена', status_code=302)


# ─── Kanban ───────────────────────────────────────────────────

@router.get('/kanban', summary='Kanban-доска', description='Drag-and-drop доска задач по статусам')
async def kanban_page(request: Request):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        ts = TaskService(session)
        cs = ClientService(session)
        user = await current_user(request)
        tasks_all = await ts.list_tasks()
        all_clients = await cs.list_clients()
        todo = [t for t in tasks_all if t.status == 'todo']
        in_progress = [t for t in tasks_all if t.status == 'in_progress']
        done = [t for t in tasks_all if t.status == 'done']
        overdue = [t for t in tasks_all if t.status == 'overdue']
    return templates.TemplateResponse(request, 'kanban.html', ctx(request, user=user,
        todo=todo, in_progress=in_progress, done=done, overdue=overdue,
        all_clients=all_clients,
        page='kanban',
    ))


@router.post('/api/tasks/{task_id}/move')
async def api_task_move(task_id: int, request: Request):
    body = await request.json()
    new_status = body.get('status')
    if new_status not in ('todo', 'in_progress', 'done', 'overdue'):
        return JSONResponse({'error': 'Неверный статус'}, status_code=400)
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return JSONResponse({'error': 'Задача не найдена'}, status_code=404)
        old_status = task.status
        task.status = new_status
        await session.commit()
    await log_activity('task', task_id, 'status_changed',
        field_name='status', old_value=old_status, new_value=new_status,
        summary=f'Задача #{task_id}: {old_status} → {new_status}')
    return JSONResponse({'ok': True})


# ─── Batch ────────────────────────────────────────────────────

@router.post('/api/tasks/batch', summary='Batch-действия', description='Массовое изменение задач')
async def api_tasks_batch(request: Request):
    body = await request.json()
    task_ids = body.get('ids', [])
    action = body.get('action')
    value = body.get('value')
    if not task_ids or not action:
        return JSONResponse({'error': 'Нужны ids и action'}, status_code=400)
    async with async_session() as session:
        for tid in task_ids:
            task = await session.get(Task, tid)
            if not task:
                continue
            if action == 'status' and value in ('todo', 'in_progress', 'done', 'overdue'):
                task.status = value
            elif action == 'priority' and value in ('low', 'medium', 'high'):
                task.priority = value
            elif action == 'client_id':
                task.client_id = int(value) if value else None
            elif action == 'delete':
                await session.execute(sa_delete(Reminder).where(Reminder.task_id == tid))
                await session.delete(task)
        await session.commit()
    return JSONResponse({'ok': True, 'affected': len(task_ids)})


# ─── API ──────────────────────────────────────────────────────

@router.post('/api/tasks/{task_id}/start')
async def api_task_start(task_id: int):
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return JSONResponse({'error': 'Задача не найдена'}, status_code=404)
        if task.status == 'todo':
            task.status = 'in_progress'
            await session.commit()
            await log_activity('task', task_id, 'status_changed',
                field_name='status', old_value='todo', new_value='in_progress',
                summary=f'Задача #{task_id} начата')
        return JSONResponse({'ok': True, 'status': task.status})


@router.get('/api/tasks')
async def api_tasks(request: Request, start: str = '', end: str = ''):
    user = await current_user(request)
    async with async_session() as session:
        ts = TaskService(session)
        all_tasks = await ts.list_tasks()
        tz = settings.tz
        now_local = datetime.now(tz)
        events = []
        for t in all_tasks:
            now_user = datetime.now(tz)
            cal_date = t.completion_date or t.deadline
            if not cal_date:
                cal_date = to_utc(now_user.replace(hour=12, minute=0, second=0, microsecond=0))
            cd = safe_dt(cal_date).astimezone(tz)
            if cd is None:
                cd = now_user.replace(hour=12, minute=0, second=0, microsecond=0)
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
            days_until = (day_start - now_local).days
            if t.status == 'done':
                color = '#6c757d'
            elif t.status == 'overdue' or days_until < 0:
                color = '#dc3545'
            elif days_until <= 2:
                color = '#ffc107'
            else:
                color = '#198754'
            client_name = t.client.org_name if t.client else ''
            notes = (t.notes[:100] + '...') if t.notes and len(t.notes) > 100 else (t.notes or '')
            checklist_progress = ''
            if t.checklist:
                done_items = sum(1 for ci in t.checklist if ci.get('done'))
                checklist_progress = f'{done_items}/{len(t.checklist)}'
            events.append({
                'id': str(t.id), 'title': f'#{t.id} {t.title}',
                'start': day_start.strftime('%Y-%m-%d'), 'end': None, 'allDay': True,
                'color': color, 'textColor': '#000' if color == '#ffc107' else '#fff',
                'status': t.status, 'client': client_name, 'priority': t.priority,
                'notes': notes, 'checklist': checklist_progress, 'task_type': t.task_type,
                'has_deadline': bool(t.deadline),
            })
            if t.checklist:
                for ci_idx, ci in enumerate(t.checklist):
                    reminder_raw = ci.get('reminder')
                    if reminder_raw and not ci.get('done'):
                        try:
                            reminder_dt = datetime.fromisoformat(reminder_raw)
                            if reminder_dt.tzinfo is None:
                                reminder_dt = reminder_dt.replace(tzinfo=tz)
                            if start and end:
                                if reminder_dt < s or reminder_dt > e:
                                    continue
                            events.append({
                                'id': f'checklist-{t.id}-{ci_idx}',
                                'title': f'📌 {t.title} → {ci.get("text", "?")}',
                                'start': reminder_dt.isoformat(),
                                'end': (reminder_dt + timedelta(hours=1)).isoformat(),
                                'allDay': False, 'color': '#0dcaf0', 'textColor': '#000',
                                'status': t.status, 'client': client_name,
                                'priority': t.priority, 'notes': notes,
                                'checklist': '', 'task_type': t.task_type,
                                'task_id': t.id, 'is_checklist': True, 'checklist_idx': ci_idx,
                            })
                        except (ValueError, TypeError):
                            pass
    return JSONResponse(events)


@router.patch('/api/tasks/{task_id}')
async def api_task_update(task_id: str, request: Request):
    body = await request.json()
    if '-' in str(task_id):
        parts = str(task_id).split('-')
        if parts[0] == 'checklist' and len(parts) == 3:
            real_task_id = int(parts[1])
            ci_idx = int(parts[2])
            async with async_session() as session:
                task = await session.get(Task, real_task_id)
                if not task:
                    return JSONResponse({'error': 'Задача не найдена'}, status_code=404)
                checklist = task.checklist or []
                if 0 <= ci_idx < len(checklist):
                    if body.get('deadline'):
                        dl = parse_web_deadline(body['deadline'])
                        if dl:
                            checklist[ci_idx]['reminder'] = dl.isoformat()
                    task.checklist = checklist
                    await session.commit()
                return JSONResponse({'ok': True, 'id': task_id})
    real_task_id = int(task_id)
    changes = []
    async with async_session() as session:
        task = await session.get(Task, real_task_id)
        if not task:
            return JSONResponse({'error': 'Задача не найдена'}, status_code=404)
        if body.get('deadline'):
            dl = parse_web_deadline(body['deadline'])
            if dl:
                task.deadline = to_utc(dl)
                changes.append('срок')
        if body.get('completion_date'):
            cd = parse_web_deadline(body['completion_date'])
            if cd:
                task.completion_date = to_utc(cd)
                changes.append('дата выполнения')
        if body.get('status'):
            old_st = task.status
            new_st = body['status']
            if old_st != new_st:
                task.status = new_st
                changes.append(f'статус: {old_st} → {new_st}')
        if 'notes' in body:
            if task.notes != body['notes']:
                task.notes = body['notes']
                changes.append('заметки')
        if 'comment' in body:
            if task.comment != body['comment']:
                task.comment = body['comment']
                changes.append('комментарий')
        if 'checklist' in body and isinstance(body['checklist'], list):
            task.checklist = body['checklist']
            changes.append('чек-лист')
        if 'recurring_interval' in body:
            task.recurring_interval = body['recurring_interval'] or None
            changes.append('повторение')
        if 'recurring_count' in body:
            new_count = int(body['recurring_count']) if body.get('recurring_count') else None
            if new_count != task.recurring_count:
                task.recurring_count = new_count
                task.recurring_remaining = new_count
                changes.append('кол-во повторений')
        if body.get('auto_start'):
            if task.status == 'todo':
                task.status = 'in_progress'
                changes.append('автостарт')
        if task.checklist:
            done_count = sum(1 for ci in task.checklist if ci.get('done'))
            total_count = len(task.checklist)
            if done_count == total_count and total_count > 0:
                if task.status != 'done':
                    task.status = 'done'
                    changes.append('автостатус')
            elif done_count > 0 and task.status == 'todo':
                task.status = 'in_progress'
                changes.append('автостатус')
            elif done_count < total_count and task.status == 'done':
                task.status = 'in_progress'
                changes.append('автостатус')
        await session.commit()
    if changes:
        await log_activity('task', real_task_id, 'updated', summary=f'Задача #{real_task_id}: {"; ".join(changes[:3])}')
    return JSONResponse({'ok': True, 'id': task_id, 'status': task.status})


@router.get('/api/tasks/all')
async def api_tasks_all(request: Request):
    user = await current_user(request)
    async with async_session() as session:
        ts = TaskService(session)
        all_tasks = await ts.list_tasks()
        tz = settings.tz
        result = []
        for t in all_tasks:
            dl = safe_dt(t.deadline).astimezone(tz) if t.deadline else None
            cd = safe_dt(t.completion_date).astimezone(tz) if t.completion_date else None
            client_name = t.client.org_name if t.client else ''
            client_id = t.client.id if t.client else None
            result.append({
                'id': t.id, 'title': t.title,
                'deadline': dl.isoformat() if dl else None,
                'completion_date': cd.isoformat() if cd else None,
                'status': t.status, 'priority': t.priority, 'task_type': t.task_type,
                'client': client_name, 'client_id': client_id,
                'notes': t.notes or '', 'comment': t.comment or '',
                'checklist': t.checklist or [], 'sort_order': t.sort_order or 0,
                'recurring_interval': t.recurring_interval,
                'recurring_count': t.recurring_count,
                'recurring_remaining': t.recurring_remaining,

            })
        return JSONResponse(result)


@router.get('/api/tasks/export/csv')
async def api_tasks_export_csv(request: Request):
    user = await current_user(request)
    async with async_session() as session:
        ts = TaskService(session)
        tasks = await ts.list_tasks()
    tz = settings.tz
    lines = ['ID,Задача,Клиент,Статус,Приоритет,Срок,Дата выполнения,Тип,Заметка']
    for t in tasks:
        dl = format_datetime(t.deadline, tz) if t.deadline else ''
        cd = format_datetime(t.completion_date, tz) if t.completion_date else ''
        client = t.client.org_name if t.client else ''
        sl = {'todo':'К выполнению','in_progress':'В работе','done':'Выполнено','overdue':'Просрочено'}.get(t.status, t.status)
        pr = {'low':'Низкий','medium':'Средний','high':'Высокий'}.get(t.priority, t.priority)
        def esc(v):
            s = str(v).replace('"', '""')
            return f'"{s}"' if ',' in s or '"' in s else s
        lines.append(','.join(map(esc, [t.id, t.title, client, sl, pr, dl, cd, t.task_type, t.notes or ''])))
    csv = '\r\n'.join(lines)
    from fastapi.responses import Response
    return Response(content=csv, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=tasks.csv'})


@router.get('/api/tasks/export/pdf')
async def api_tasks_export_pdf(request: Request):
    user = await current_user(request)
    async with async_session() as session:
        ts = TaskService(session)
        tasks = await ts.list_tasks()
    tz = settings.tz
    rows = ''
    for t in tasks:
        dl = format_datetime(t.deadline, tz) if t.deadline else '—'
        client = t.client.org_name if t.client else '—'
        sl = {'todo':'К выполнению','in_progress':'В работе','done':'Выполнено','overdue':'Просрочено'}.get(t.status, t.status)
        pr = {'low':'Низкий','medium':'Средний','high':'Высокий'}.get(t.priority, t.priority)
        rows += f'<tr><td>{t.id}</td><td>{t.title}</td><td>{client}</td><td>{sl}</td><td>{pr}</td><td>{dl}</td></tr>\n'
    html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>TaskFlow — задачи</title>
<style>body{{font-family:sans-serif;font-size:12px;}}table{{width:100%;border-collapse:collapse;}}
th,td{{border:1px solid #999;padding:4px 6px;text-align:left;}}th{{background:#eee;}}
h1{{font-size:18px;}}</style></head><body>
<h1>TaskFlow — список задач</h1>
<p>Дата: <strong>{datetime.now(tz).strftime('%d.%m.%Y %H:%M')}</strong> | Всего: <strong>{len(tasks)}</strong></p>
<table><thead><tr><th>#</th><th>Задача</th><th>Клиент</th><th>Статус</th><th>Приоритет</th><th>Срок</th></tr></thead><tbody>{rows}</tbody></table></body></html>'''
    return HTMLResponse(content=html)


@router.get('/api/reports/export/csv')
async def api_reports_export_csv(request: Request):
    async with async_session() as session:
        ts = TaskService(session)
        tasks = await ts.list_tasks()
        cs = ClientService(session)
        clients = await cs.list_clients()
    status_dist = {'todo': 0, 'in_progress': 0, 'done': 0, 'overdue': 0}
    for t in tasks:
        s = t.status if t.status in status_dist else 'other'
        if s in status_dist:
            status_dist[s] += 1
    slabel = {'todo':'К выполнению','in_progress':'В работе','done':'Выполнено','overdue':'Просрочено'}
    lines = ['Показатель,Значение']
    lines.append(f'Всего задач,{len(tasks)}')
    for k, v in status_dist.items():
        lines.append(f'{slabel.get(k, k)},{v}')
    lines.append(f'Всего клиентов,{len(clients)}')
    lines.append(f'Активных клиентов,{sum(1 for c in clients if c.status == "active")}')
    csv = '\r\n'.join(lines)
    from fastapi.responses import Response
    return Response(content=csv, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=report.csv'})


@router.patch('/api/tasks/{task_id}/checklist-item')
async def api_checklist_item_update(task_id: int, request: Request):
    body = await request.json()
    idx = body.get('index')
    async with async_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return JSONResponse({'error': 'Задача не найдена'}, status_code=404)
        checklist = task.checklist or []
        if idx is None or idx < 0 or idx >= len(checklist):
            return JSONResponse({'error': 'Неверный индекс'}, status_code=400)
        if 'done' in body:
            checklist[idx]['done'] = body['done']
        if body.get('text'):
            checklist[idx]['text'] = body['text']
        if 'reminder' in body:
            if body['reminder']:
                checklist[idx]['reminder'] = body['reminder']
            else:
                checklist[idx].pop('reminder', None)
        task.checklist = checklist
        old_status = task.status
        done_count = sum(1 for ci in checklist if ci.get('done'))
        total_count = len(checklist)
        if done_count == total_count and total_count > 0:
            if task.status != 'done':
                task.status = 'done'
        elif done_count > 0 and task.status == 'todo':
            task.status = 'in_progress'
        elif done_count < total_count and task.status == 'done':
            task.status = 'in_progress'
        await session.commit()
        if old_status != task.status:
            await log_activity('task', task_id, 'status_changed',
                field_name='status', old_value=old_status, new_value=task.status,
                summary=f'Задача #{task_id}: чек-лист → {task.status}')
        ci_text = checklist[idx].get('text', '')[:80]
        if 'done' in body:
            await log_activity('task', task_id, 'checklist_toggle',
                field_name=f'checklist[{idx}]',
                summary=f'Чек-лист #{task_id}: "{ci_text}" → {"выполнено" if body["done"] else "не выполнено"}')
        return JSONResponse({'ok': True, 'checklist': checklist, 'auto_status': task.status})


@router.get('/api/clients')
async def api_clients(request: Request):
    user = await current_user(request)
    async with async_session() as session:
        cs = ClientService(session)
        clients = await cs.list_clients()
        return JSONResponse([{
            'id': c.id, 'org_name': c.org_name, 'domain': c.domain or '',
            'accesses': c.accesses or [],
            'contract_end': format_datetime(c.contract_end, settings.tz) if c.contract_end else '',
        } for c in clients])


@router.get('/api/templates')
async def api_templates():
    return JSONResponse(CHECKLIST_TEMPLATES)


@router.post('/api/templates')
async def api_templates_save(request: Request):
    if not await require_auth(request):
        return JSONResponse({'error': 'auth'}, status_code=401)
    try:
        body = await request.json()
        for key in body:
            if key in CHECKLIST_TEMPLATES and isinstance(body[key], list):
                CHECKLIST_TEMPLATES[key] = body[key]
        return JSONResponse({'ok': True})
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=400)


# ─── Calendar ─────────────────────────────────────────────────

@router.get('/calendar', summary='Календарь', description='Календарное представление задач с FullCalendar')
async def calendar_page(request: Request):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        cs = ClientService(session)
        user = await current_user(request)
        all_clients = await cs.list_clients()
        result = await session.execute(select(UserSettings).where(UserSettings.id == 1))
        us = result.scalar_one_or_none()
        cal_view_mode = us.calendar_view_mode if us else 'time'
    return templates.TemplateResponse(request, 'calendar.html', ctx(request, user=user,
        page='calendar',
        all_clients=all_clients,
        calendar_view_mode=cal_view_mode,
        CHECKLIST_TEMPLATES=CHECKLIST_TEMPLATES,
        checklist_templates_json=json.dumps(CHECKLIST_TEMPLATES, ensure_ascii=False),
    ))


# ─── Clients ──────────────────────────────────────────────────

@router.get('/clients', summary='Список клиентов', description='Страница со списком всех клиентов с фильтрацией и пагинацией')
async def clients_page(
    request: Request,
    status_filter: str = '',
    search: str = '',
    sort: str = 'name',
    order: str = 'asc',
    page: int = Query(1, ge=1),
):
    user = await current_user(request)
    if not user:
        return RedirectResponse(url='/login')
    per_page = 20
    async with async_session() as session:
        cs = ClientService(session)
        clients = await cs.list_clients()

    if status_filter:
        clients = [c for c in clients if c.status == status_filter]
    if search:
        clients = [c for c in clients if search.lower() in c.org_name.lower() or (c.domain and search.lower() in c.domain.lower())]

    if sort == 'contract_end':
        clients.sort(key=lambda c: to_tz(c.contract_end) or datetime.max.replace(tzinfo=settings.tz), reverse=(order == 'desc'))
    elif sort == 'tasks':
        clients.sort(key=lambda c: len([t for t in c.tasks if t.status not in ('done',)]) if c.tasks else 0, reverse=(order == 'desc'))
    else:
        clients.sort(key=lambda c: c.org_name.lower(), reverse=(order == 'desc'))

    total = len(clients)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start_index = (page - 1) * per_page
    clients_page_list = clients[start_index:start_index + per_page]

    return templates.TemplateResponse(request, 'clients.html', ctx(request, user=user,
        clients=clients_page_list,
        total=total,
        page_num=page,
        total_pages=total_pages,
        status_filter=status_filter,
        search=search,
        sort=sort,
        order=order,
        page='clients',
    ))


@router.get('/clients/{client_id}')
async def client_detail(request: Request, client_id: int):
    user = await current_user(request)
    if not user:
        return RedirectResponse(url='/login')
    async with async_session() as session:
        cs = ClientService(session)
        ts = TaskService(session)
        client = await cs.get_client(client_id)
        if not client:
            return RedirectResponse(url='/clients?error=Клиент не найден')
        tasks = await ts.list_tasks(client_id=client_id)
        upcoming = [t for t in tasks if t.deadline and safe_dt(t.deadline) > utc_now() and t.status != 'done']
        upcoming.sort(key=lambda t: safe_dt(t.deadline))
        all_tasks_list = await ts.list_tasks()

    return templates.TemplateResponse(request, 'client_detail.html', ctx(request, user=user,
        client=client,
        tasks=tasks,
        upcoming_tasks=upcoming[:7],
        all_tasks=all_tasks_list,
        page='clients',
    ))


@router.post('/clients/create')
async def client_create(
    request: Request,
    org_name: str = Form(...),
    domain: str | None = Form(None),
    contract_start: str | None = Form(None),
    contract_end: str = Form(...),
    org_data: str | None = Form(None),
    accesses_raw: str | None = Form(None),
):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    errors = []
    end = parse_web_deadline(contract_end)
    if not end:
        errors.append(f'Не удалось распознать дату окончания: {contract_end}')
    start = None
    if contract_start:
        start = parse_web_deadline(contract_start)
    if not start:
        start = utc_now()
    if errors:
        return RedirectResponse(url='/clients?error=' + '; '.join(errors), status_code=302)

    import contextlib
    accesses = None
    if accesses_raw and accesses_raw.strip():
        with contextlib.suppress(json.JSONDecodeError):
            accesses = json.loads(accesses_raw)

    async with async_session() as session:
        cs = ClientService(session)
        await cs.create_client(
            org_name=org_name.strip(),
            domain=domain or None,
            contract_start=start,
            contract_end=end,
            org_data=org_data or None,
            accesses=accesses,
        )
    await log_activity('client', None, 'created', summary=f'Создан клиент: {org_name.strip()}')
    return RedirectResponse(url='/clients?success=Клиент создан', status_code=302)


@router.post('/clients/{client_id}/status')
async def client_status(request: Request, client_id: int, status: str = Form(...)):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        c = await session.get(Client, client_id)
        old_status = c.status if c else ''
        cs = ClientService(session)
        await cs.update_status(client_id, status)
    await log_activity('client', client_id, 'status_changed',
        field_name='status', old_value=old_status, new_value=status,
        summary=f'Клиент #{client_id}: {old_status} → {status}')
    return RedirectResponse(url='/clients', status_code=302)


@router.post('/clients/{client_id}/update')
async def client_update(
    request: Request,
    client_id: int,
    org_name: str = Form(...),
    domain: str | None = Form(None),
    contract_start: str | None = Form(None),
    contract_end: str = Form(...),
    org_data: str | None = Form(None),
    accesses_raw: str | None = Form(None),
):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            return RedirectResponse(url='/clients?error=Клиент не найден')
        end = parse_web_deadline(contract_end)
        start = None
        if contract_start:
            start = parse_web_deadline(contract_start)
        if end:
            changes = []
            if client.org_name != org_name.strip():
                changes.append('название')
            client.org_name = org_name.strip()
            client.domain = domain or None
            client.contract_end = to_utc(end)
            if start:
                client.contract_start = to_utc(start)
                changes.append('дата начала')
            client.org_data = org_data or None
            if accesses_raw and accesses_raw.strip():
                try:
                    client.accesses = json.loads(accesses_raw)
                    changes.append('доступы')
                except json.JSONDecodeError:
                    pass
            else:
                client.accesses = None
            await session.commit()
            if changes:
                await log_activity('client', client_id, 'updated', summary=f'Клиент #{client_id}: {"; ".join(changes)}')
    return RedirectResponse(url=f'/clients/{client_id}?success=Сохранено', status_code=302)


@router.post('/clients/{client_id}/delete')
async def client_delete(request: Request, client_id: int):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    now = utc_now()
    async with async_session() as session:
        c = await session.get(Client, client_id, options=[selectinload(Client.tasks)])
        if c:
            c.deleted_at = now
            c.status = 'closed'
            for t in c.tasks:
                t.deleted_at = now
        await session.commit()
    await log_activity('client', client_id, 'deleted', summary=f'Клиент #{client_id} перемещён в корзину')
    ref = request.headers.get('Referer', '/clients')
    return RedirectResponse(url=ref, status_code=303)


# ─── Settings ─────────────────────────────────────────────────

@router.get('/settings', summary='Настройки', description='Страница настроек пользователя')
async def settings_page(request: Request):
    user = await current_user(request)
    if not user:
        return RedirectResponse(url='/login')
    async with async_session() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.id == 1))
        us = result.scalar_one_or_none()
        if not us:
            us = UserSettings(id=1, timezone=settings.DEFAULT_TIMEZONE, default_reminder_offset_hours=1)
            session.add(us)
            await session.commit()
    return templates.TemplateResponse(request, 'settings.html', ctx(request, user=user,
        settings=us,
        templates=CHECKLIST_TEMPLATES,
        page='settings',
    ))


@router.post('/settings')
async def settings_save(
    request: Request,
    timezone: str = Form(...),
    reminder_offset: int = Form(1),
    calendar_view_mode: str = Form('time'),
):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.id == 1))
        us = result.scalar_one_or_none()
        if not us:
            us = UserSettings(id=1)
            session.add(us)
        us.timezone = timezone
        us.default_reminder_offset_hours = reminder_offset
        us.calendar_view_mode = calendar_view_mode if calendar_view_mode in ('time', 'list') else 'time'
        us.last_sync = utc_now()
        await session.commit()
    settings.DEFAULT_TIMEZONE = timezone
    return RedirectResponse(url='/settings?success=Настройки сохранены', status_code=302)


# ─── Notifications ────────────────────────────────────────────

NOTIFICATION_ICONS = {
    'overdue': 'bi-exclamation-triangle-fill text-danger',
    'deadline': 'bi-bell-fill text-warning',
    'checklist': 'bi-list-check text-info',
    'publish': 'bi-megaphone-fill text-success',
    'contract': 'bi-file-earmark-text text-primary',
}


@router.get('/notifications', summary='Уведомления', description='Страница уведомлений')
async def notifications_page(request: Request):
    user = await current_user(request)
    if not user:
        return RedirectResponse(url='/login')
    async with async_session() as session:
        ns = NotificationService(session)
        notifications = await ns.list_notifications(limit=200)
        unread_count = await ns.get_unread_count()
    return templates.TemplateResponse(request, 'notifications.html', ctx(request, user=user,
        notifications=notifications,
        unread_count=unread_count,
        icons=NOTIFICATION_ICONS,
        page='notifications',
    ))


@router.get('/api/notifications')
async def api_notifications(unread_only: bool = False, limit: int = 100):
    async with async_session() as session:
        ns = NotificationService(session)
        notifications = await ns.list_notifications(unread_only=unread_only, limit=limit)
        unread_count = await ns.get_unread_count()
        tz = settings.tz
        return JSONResponse({
            'unread_count': unread_count,
            'notifications': [{
                'id': n.id,
                'type': n.notification_type,
                'title': n.title,
                'message': n.message or '',
                'task_id': n.task_id,
                'client_id': n.client_id,
                'checklist_idx': n.checklist_idx,
                'read': n.read,
                'created_at': n.created_at.astimezone(tz).isoformat() if n.created_at else '',
            } for n in notifications],
        })


@router.post('/api/notifications/{notif_id}/read')
async def api_notification_read(notif_id: int):
    async with async_session() as session:
        ns = NotificationService(session)
        await ns.mark_read(notif_id)
    return JSONResponse({'ok': True})


@router.post('/api/notifications/read-all')
async def api_notifications_read_all():
    async with async_session() as session:
        ns = NotificationService(session)
        notifs = await ns.list_notifications(unread_only=True)
        for n in notifs:
            await ns.mark_read(n.id)
    return JSONResponse({'ok': True})


@router.post('/api/notifications/{notif_id}/dismiss')
async def api_notification_dismiss(notif_id: int):
    async with async_session() as session:
        ns = NotificationService(session)
        await ns.dismiss(notif_id)
    return JSONResponse({'ok': True})


@router.get('/api/notifications/unread-count')
async def api_notifications_unread_count():
    async with async_session() as session:
        ns = NotificationService(session)
        count = await ns.get_unread_count()
    return JSONResponse({'count': count})


# ─── Search ────────────────────────────────────────────────────

@router.get('/api/search')
async def api_search(q: str = ''):
    if not q or not q.strip():
        return JSONResponse({'tasks': [], 'clients': []})
    q = q.strip()
    like = f'%{q}%'
    async with async_session() as session:
        tasks = await session.execute(
            select(Task).where(
                Task.deleted_at.is_(None),
                (Task.title.ilike(like)) | (Task.notes.ilike(like)) | (Task.comment.ilike(like))
            ).limit(10)
        )
        clients = await session.execute(
            select(Client).where(
                Client.deleted_at.is_(None),
                (Client.org_name.ilike(like)) | (Client.domain.ilike(like))
            ).limit(5)
        )
    return JSONResponse({
        'tasks': [{'id': t.id, 'title': t.title[:80], 'status': t.status} for t in tasks.scalars()],
        'clients': [{'id': c.id, 'org_name': c.org_name} for c in clients.scalars()],
    })


# ─── Activity Log / Audit ──────────────────────────────────────

@router.get('/activity', summary='Activity log', description='Журнал действий')
async def activity_page(request: Request):
    user = await current_user(request)
    if not user:
        return RedirectResponse(url='/login')
    entity_type = request.query_params.get('entity_type', '')
    entity_id_raw = request.query_params.get('entity_id', '')
    entity_id = int(entity_id_raw) if entity_id_raw and entity_id_raw.isdigit() else None
    logs = await list_activity(limit=500, entity_type=entity_type or None, entity_id=entity_id)
    return templates.TemplateResponse(request, 'activity.html', ctx(request, user=user,
        logs=logs, page='activity',
        filter_type=entity_type, filter_id=entity_id,
    ))


@router.get('/api/activity')
async def api_activity(limit: int = 200, entity_type: str = '', entity_id: str = ''):
    eid = int(entity_id) if entity_id and entity_id.isdigit() else None
    logs = await list_activity(limit=limit, entity_type=entity_type or None, entity_id=eid)
    tz = settings.tz
    return JSONResponse([{
        'id': log.id,
        'entity_type': log.entity_type,
        'entity_id': log.entity_id,
        'action': log.action,
        'field_name': log.field_name,
        'old_value': log.old_value,
        'new_value': log.new_value,
        'summary': log.summary,
        'created_at': log.created_at.astimezone(tz).isoformat() if log.created_at else '',
    } for log in logs])


# ─── Trash / Restore ───────────────────────────────────────────

@router.get('/trash')
async def trash_page(request: Request):
    user = await current_user(request)
    if not user:
        return RedirectResponse(url='/login')
    async with async_session() as session:
        tasks = (await session.execute(
            select(Task).options(selectinload(Task.client)).where(Task.deleted_at.is_not(None)).order_by(Task.deleted_at.desc()).limit(50)
        )).scalars().all()
        clients = (await session.execute(
            select(Client).options(selectinload(Client.tasks)).where(Client.deleted_at.is_not(None)).order_by(Client.deleted_at.desc()).limit(50)
        )).scalars().all()
    return templates.TemplateResponse(request, 'trash.html', ctx(request, user=user,
        page='trash', deleted_tasks=tasks, deleted_clients=clients,
    ))


@router.post('/api/tasks/{task_id}/delete')
async def api_task_delete(task_id: int):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if t and not t.deleted_at:
            t.deleted_at = utc_now()
            await session.commit()
    await log_activity('task', task_id, 'deleted', summary=f'Задача #{task_id} перемещена в корзину')
    return JSONResponse({'ok': True})


@router.post('/tasks/{task_id}/delete')
async def task_delete(request: Request, task_id: int):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if t and not t.deleted_at:
            t.deleted_at = utc_now()
            await session.commit()
    await log_activity('task', task_id, 'deleted', summary=f'Задача #{task_id} перемещена в корзину')
    ref = request.headers.get('Referer', '/tasks')
    return RedirectResponse(url=ref, status_code=303)


@router.post('/api/tasks/{task_id}/restore')
async def api_task_restore(task_id: int):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if t and t.deleted_at:
            t.deleted_at = None
            t.status = 'todo'
            await session.commit()
    await log_activity('task', task_id, 'restored', summary=f'Задача #{task_id} восстановлена из корзины')
    return JSONResponse({'ok': True})


@router.post('/tasks/{task_id}/restore')
async def task_restore(request: Request, task_id: int):
    if not await require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if t and t.deleted_at:
            t.deleted_at = None
            t.status = 'todo'
            await session.commit()
    await log_activity('task', task_id, 'restored', summary=f'Задача #{task_id} восстановлена из корзины')
    ref = request.headers.get('Referer', '/tasks')
    return RedirectResponse(url=ref, status_code=303)


@router.post('/api/clients/{client_id}/restore')
@router.post('/clients/{client_id}/restore')
async def api_client_restore(client_id: int):
    async with async_session() as session:
        from sqlalchemy.orm import selectinload
        c = await session.get(Client, client_id, options=[selectinload(Client.tasks)])
        if c and c.deleted_at:
            c.deleted_at = None
            c.status = 'active'
            for t in c.tasks:
                t.deleted_at = None
            await session.commit()
    await log_activity('client', client_id, 'restored', summary=f'Клиент #{client_id} восстановлен из корзины')
    return JSONResponse({'ok': True})


@router.post('/api/tasks/{task_id}/hard-delete')
async def api_task_hard_delete(task_id: int):
    async with async_session() as session:
        await session.execute(sa_delete(FileAttachment).where(FileAttachment.task_id == task_id))
        await session.execute(sa_delete(Task).where(Task.id == task_id))
        await session.commit()
    return JSONResponse({'ok': True})


@router.post('/api/clients/{client_id}/hard-delete')
async def api_client_hard_delete(client_id: int):
    now = utc_now()
    cutoff = now - timedelta(days=30)
    async with async_session() as session:
        c = await session.get(Client, client_id)
        if c and c.deleted_at and c.deleted_at < cutoff:
            await session.execute(sa_delete(Task).where(Task.client_id == client_id))
            await session.execute(sa_delete(Client).where(Client.id == client_id))
            await session.commit()
            return JSONResponse({'ok': True})
    return JSONResponse({'ok': False, 'error': 'Клиента нет в корзине или прошло менее 30 дней'}, status_code=400)


# ─── Print / Export ────────────────────────────────────────────

@router.get('/tasks/{task_id}/print')
async def task_print(task_id: int):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if not t:
            return HTMLResponse('Task not found', status_code=404)
        cname = t.client.org_name if t.client else ''
        dl = safe_dt(t.deadline).astimezone(settings.tz).strftime('%d.%m.%Y %H:%M') if t.deadline else ''
        cd = safe_dt(t.completion_date).astimezone(settings.tz).strftime('%d.%m.%Y %H:%M') if t.completion_date else ''
        created = safe_dt(t.created_at).astimezone(settings.tz).strftime('%d.%m.%Y %H:%M') if t.created_at else ''
        status_label = {'todo':'К выполнению','in_progress':'В работе','done':'Выполнено','overdue':'Просрочено'}.get(t.status, t.status)
        priority_label = {'low':'Низкий','medium':'Средний','high':'Высокий'}.get(t.priority, t.priority)
        checklist = t.checklist or []
    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Задача #{t.id}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 20px auto; padding: 20px; color: #222; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #333; padding-bottom: 8px; margin-bottom: 16px; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }}
  .meta div {{ padding: 4px 0; }}
  .label {{ font-weight: 600; color: #555; font-size: 12px; text-transform: uppercase; }}
  .value {{ font-size: 14px; }}
  p {{ white-space: pre-wrap; margin: 4px 0 12px; line-height: 1.5; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #ddd; font-size: 13px; }}
  th {{ background: #f5f5f5; }}
  .done {{ text-decoration: line-through; color: #999; }}
  .client {{ margin-top: 20px; padding-top: 12px; border-top: 1px solid #ccc; font-size: 13px; color: #666; }}
  @media print {{ body {{ margin: 0; padding: 10px; }} .no-print {{ display: none; }} }}
</style></head><body>
<div class="no-print" style="margin-bottom:12px"><button onclick="window.print()">Печать / PDF</button> <button onclick="window.close()">Закрыть</button></div>
<h1>Задача #{t.id}: {t.title}</h1>
<div class="meta">
  <div><div class="label">Статус</div><div class="value">{status_label}</div></div>
  <div><div class="label">Приоритет</div><div class="value">{priority_label}</div></div>
  <div><div class="label">Тип</div><div class="value">{t.task_type}</div></div>
  <div><div class="label">Клиент</div><div class="value">{cname or '—'}</div></div>
  <div><div class="label">Срок</div><div class="value">{dl or '—'}</div></div>
  <div><div class="label">Дата выполнения</div><div class="value">{cd or '—'}</div></div>
  <div><div class="label">Создана</div><div class="value">{created}</div></div>
</div>
'''
    if t.notes:
        html += f'<h3>Заметки</h3><p>{t.notes}</p>'
    if t.comment:
        html += f'<h3>Комментарий</h3><p>{t.comment}</p>'
    if checklist:
        html += '<h3>Чек-лист</h3><table><thead><tr><th style="width:30px"></th><th>Пункт</th></tr></thead><tbody>'
        for ci in checklist:
            cls = ' class="done"' if ci.get('done') else ''
            html += f'<tr><td>[{"x" if ci.get("done") else " "}]</td><td{cls}>{ci.get("text","")}</td></tr>'
        html += '</tbody></table>'
    if cname:
        html += f'<div class="client">Клиент: {cname}</div>'
    html += '</body></html>'
    return HTMLResponse(html)


@router.get('/clients/{client_id}/print')
async def client_print(client_id: int):
    async with async_session() as session:
        c = await session.get(Client, client_id)
        if not c:
            return HTMLResponse('Client not found', status_code=404)
        tasks = (await session.execute(select(Task).where(Task.client_id == client_id, Task.deleted_at.is_(None)))).scalars().all()
        start = safe_dt(c.contract_start).astimezone(settings.tz).strftime('%d.%m.%Y') if c.contract_start else ''
        end = safe_dt(c.contract_end).astimezone(settings.tz).strftime('%d.%m.%Y') if c.contract_end else ''
        status_label = {'active':'Активен','paused':'Пауза','closed':'Закрыт'}.get(c.status, c.status)
    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Клиент {c.org_name}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 20px auto; padding: 20px; color: #222; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #333; padding-bottom: 8px; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin: 12px 0; }}
  .meta div {{ padding: 4px 0; }}
  .label {{ font-weight: 600; color: #555; font-size: 12px; text-transform: uppercase; }}
  .value {{ font-size: 14px; }}
  pre {{ white-space: pre-wrap; margin: 4px 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #ddd; font-size: 13px; }}
  th {{ background: #f5f5f5; }}
  @media print {{ body {{ margin: 0; padding: 10px; }} .no-print {{ display: none; }} }}
</style></head><body>
<div class="no-print" style="margin-bottom:12px"><button onclick="window.print()">Печать / PDF</button> <button onclick="window.close()">Закрыть</button></div>
<h1>{c.org_name}</h1>
<div class="meta">
  <div><div class="label">Статус</div><div class="value">{status_label}</div></div>
  <div><div class="label">Домен</div><div class="value">{c.domain or '—'}</div></div>
  <div><div class="label">Договор</div><div class="value">{start} — {end}</div></div>
</div>
'''
    if c.org_data:
        html += f'<h3>Данные организации</h3><pre>{c.org_data}</pre>'
    if c.accesses:
        html += '<h3>Доступы</h3><table><thead><tr><th>Сервис</th><th>URL</th><th>Логин</th><th>Пароль</th></tr></thead><tbody>'
        for acc in c.accesses:
            html += f'<tr><td>{acc.get("title","")}</td><td>{acc.get("url","")}</td><td>{acc.get("login","")}</td><td>{acc.get("password","")}</td></tr>'
        html += '</tbody></table>'
    if tasks:
        html += '<h3>Задачи</h3><table><thead><tr><th>#</th><th>Название</th><th>Статус</th><th>Срок</th></tr></thead><tbody>'
        for t in tasks:
            dl = safe_dt(t.deadline).astimezone(settings.tz).strftime('%d.%m.%Y') if t.deadline else ''
            sl = {'todo':'К выполнению','in_progress':'В работе','done':'Выполнено','overdue':'Просрочено'}.get(t.status, t.status)
            html += f'<tr><td>{t.id}</td><td>{t.title}</td><td>{sl}</td><td>{dl}</td></tr>'
        html += '</tbody></table>'
    html += '</body></html>'
    return HTMLResponse(html)


# ─── File Attachments ──────────────────────────────────────────

from fastapi import UploadFile
from fastapi.responses import HTMLResponse


@router.post('/api/tasks/{task_id}/upload')
async def api_task_upload(task_id: int, file: UploadFile):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if not t:
            return JSONResponse({'error': 'Task not found'}, status_code=404)
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


@router.get('/api/files/{file_id}/download')
async def api_file_download(file_id: int):
    async with async_session() as session:
        att = await session.get(FileAttachment, file_id)
        if not att:
            return JSONResponse({'error': 'File not found'}, status_code=404)
        from fastapi.responses import Response
        return Response(
            content=att.data,
            media_type=att.content_type or 'application/octet-stream',
            headers={'Content-Disposition': f'attachment; filename="{att.original_name}"'},
        )


@router.get('/api/tasks/{task_id}/files')
async def api_task_files(task_id: int):
    async with async_session() as session:
        files = (await session.execute(
            select(FileAttachment).where(FileAttachment.task_id == task_id).order_by(FileAttachment.uploaded_at)
        )).scalars().all()
    return JSONResponse([
        {'id': f.id, 'name': f.original_name, 'size': f.size, 'content_type': f.content_type,
         'uploaded_at': format_datetime(f.uploaded_at, settings.tz) if f.uploaded_at else ''}
        for f in files
    ])


@router.delete('/api/files/{file_id}')
async def api_file_delete(file_id: int):
    async with async_session() as session:
        await session.execute(sa_delete(FileAttachment).where(FileAttachment.id == file_id))
        await session.commit()
    return JSONResponse({'ok': True})


# ─── Recurring Tasks ────────────────────────────────────────────

def _next_recurring_date(from_dt: datetime, interval: str) -> datetime | None:
    if interval == 'daily':
        return from_dt + timedelta(days=1)
    elif interval == 'weekly':
        return from_dt + timedelta(weeks=1)
    elif interval == 'monthly':
        import calendar
        month = from_dt.month + 1
        year = from_dt.year
        if month > 12:
            month = 1
            year += 1
        day = min(from_dt.day, calendar.monthrange(year, month)[1])
        try:
            return from_dt.replace(year=year, month=month, day=day)
        except (ValueError, OverflowError):
            return from_dt + timedelta(days=30)
    return None


@router.post('/api/tasks/{task_id}/generate-next')
async def api_generate_next(task_id: int):
    async with async_session() as session:
        t = await session.get(Task, task_id)
        if not t or not t.recurring_interval or (t.recurring_remaining is not None and t.recurring_remaining <= 0):
            return JSONResponse({'ok': False, 'error': 'Not recurring or limit reached'})
        next_dl = _next_recurring_date(safe_dt(t.deadline) if t.deadline else utc_now(), t.recurring_interval)
        next_cd = _next_recurring_date(safe_dt(t.completion_date) if t.completion_date else utc_now(), t.recurring_interval) if t.completion_date else None
        nt = Task(
            client_id=t.client_id,
            title=t.title,
            task_type=t.task_type,
            notes=t.notes,
            comment=t.comment,
            deadline=next_dl,
            completion_date=next_cd,
            status='todo',
            priority=t.priority,
            checklist=t.checklist,
            recurring_interval=t.recurring_interval,
            recurring_count=t.recurring_count,
            recurring_remaining=(t.recurring_remaining - 1) if t.recurring_remaining is not None else None,
            recurring_parent_id=t.recurring_parent_id or t.id,
        )
        session.add(nt)
        if t.recurring_remaining is not None:
            t.recurring_remaining -= 1
            if t.recurring_remaining <= 0:
                t.recurring_interval = None
        await session.commit()
        return JSONResponse({'ok': True, 'new_id': nt.id})
