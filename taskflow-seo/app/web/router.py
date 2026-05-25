from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
import json

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy import delete as sa_delete

from app.core.config import settings
from app.core.database import async_session
from app.core.models import Task, Client, UserSettings, Reminder
from app.core.utils.timezone import utc_now, format_datetime, to_utc
from app.services.task_service import TaskService
from app.services.client_service import ClientService
from app.web.app import templates, check_auth, AUTH_TOKEN, SECRET_COOKIE

router = APIRouter()

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


def require_auth(request: Request):
    if not check_auth(request):
        return False
    return True


def safe_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo('UTC'))
    return dt


def to_tz(dt: Optional[datetime]) -> Optional[datetime]:
    dt = safe_dt(dt)
    if dt is None:
        return None
    return dt.astimezone(settings.tz)


def ctx(request: Request, **kw) -> dict:
    tz = settings.tz
    base = {
        'request': request,
        'now': datetime.now(tz),
        'tz': tz,
        'to_tz': to_tz,
        'format_dt': format_datetime,
    }
    base.update(kw)
    return base


def parse_web_deadline(text: str) -> Optional[datetime]:
    if not text or not text.strip():
        return None
    from app.core.utils.timezone import parse_deadline
    return parse_deadline(text.strip(), settings.tz)


# ─── Auth ─────────────────────────────────────────────────────

@router.get('/login')
async def login_page(request: Request):
    return templates.TemplateResponse('login.html', {'request': request})


@router.post('/login')
async def login_post(request: Request, secret: str = Form(...)):
    if secret == AUTH_TOKEN:
        resp = RedirectResponse(url='/', status_code=302)
        resp.set_cookie(key=SECRET_COOKIE, value=AUTH_TOKEN, httponly=True, max_age=86400 * 30)
        return resp
    return templates.TemplateResponse('login.html', {'request': request, 'error': 'Неверный ключ'})


@router.get('/logout')
async def logout():
    resp = RedirectResponse(url='/login', status_code=302)
    resp.delete_cookie(SECRET_COOKIE)
    return resp


# ─── Dashboard ────────────────────────────────────────────────

@router.get('/')
async def dashboard(request: Request):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        ts = TaskService(session)
        cs = ClientService(session)
        tz = settings.tz
        tasks_all = await ts.list_tasks()
        overdue = [t for t in tasks_all if t.status == 'overdue']
        due_today = await ts.get_tasks_due_today(tz)
        done = [t for t in tasks_all if t.status == 'done']
        clients = await cs.list_clients()
        active_clients = [c for c in clients if c.status == 'active']
        ending_soon = await cs.get_clients_ending_soon(days=14)

    return templates.TemplateResponse('dashboard.html', ctx(request,
        overdue_count=len(overdue),
        today_count=len(due_today),
        total_tasks=len(tasks_all),
        done_tasks=len(done),
        active_clients=len(active_clients),
        ending_clients=len(ending_soon),
        overdue_tasks=overdue[:5],
        today_tasks=due_today[:5],
        ending_clients_list=ending_soon[:5],
        page='dashboard',
    ))


# ─── Tasks ────────────────────────────────────────────────────

@router.get('/tasks')
async def tasks_page(
    request: Request,
    status: str = '',
    search: str = '',
    sort: str = 'deadline',
    order: str = 'asc',
    client_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    per_page = 20
    async with async_session() as session:
        ts = TaskService(session)
        cs = ClientService(session)
        tz = settings.tz

        found_client_id = client_id
        if search and '.' in search:
            client = await cs.get_client_by_domain(search)
            if client:
                found_client_id = client.id
        elif search:
            clients = await cs.search_clients(search)
            if clients and found_client_id is None:
                found_client_id = clients[0].id

        tasks = await ts.list_tasks(
            status=status if status else None,
            client_id=found_client_id,
        )
        all_clients = await cs.list_clients()

    if search and not found_client_id:
        tasks = [t for t in tasks if search.lower() in t.title.lower()]

    if sort == 'priority':
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        tasks.sort(key=lambda t: priority_order.get(t.priority, 1), reverse=(order == 'desc'))
    elif sort == 'created':
        tasks.sort(key=lambda t: safe_dt(t.created_at) or datetime(9999, 12, 31, tzinfo=ZoneInfo('UTC')), reverse=(order == 'desc'))
    elif sort == 'status':
        status_order = {'overdue': 0, 'todo': 1, 'in_progress': 2, 'done': 3}
        tasks.sort(key=lambda t: status_order.get(t.status, 4), reverse=(order == 'desc'))
    else:
        tasks.sort(key=lambda t: safe_dt(t.deadline) or datetime(9999, 12, 31, tzinfo=ZoneInfo('UTC')), reverse=(order == 'desc'))

    total = len(tasks)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start_index = (page - 1) * per_page
    tasks_page = tasks[start_index:start_index + per_page]

    return templates.TemplateResponse('tasks.html', ctx(request,
        tasks=tasks_page,
        total=total,
        page=page,
        total_pages=total_pages,
        status=status,
        search=search,
        sort=sort,
        order=order,
        client_id=client_id,
        page_name='tasks',
        all_clients=all_clients,
        checklist_templates_json=json.dumps(CHECKLIST_TEMPLATES, ensure_ascii=False),
    ))


@router.post('/tasks/create')
async def task_create(
    request: Request,
    title: str = Form(...),
    client_id: Optional[int] = Form(None),
    deadline: Optional[str] = Form(None),
    task_type: str = Form('custom'),
    priority: str = Form('medium'),
    notes: Optional[str] = Form(None),
    comment: Optional[str] = Form(None),
    checklist_raw: Optional[str] = Form(None),
):
    if not require_auth(request):
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
        if errors:
            return RedirectResponse(url='/tasks?error=' + '; '.join(errors), status_code=302)

        checklist = None
        if checklist_raw and checklist_raw.strip():
            try:
                checklist = json.loads(checklist_raw)
            except json.JSONDecodeError:
                pass

        async with async_session() as session:
            ts = TaskService(session)
            await ts.create_task(
                title=title.strip(),
                client_id=client_id if client_id else None,
                task_type=task_type,
                deadline=dl,
                priority=priority,
                notes=notes,
                comment=comment,
                checklist=checklist,
            )
        return RedirectResponse(url='/tasks?success=Задача создана', status_code=302)
    except Exception as e:
        return RedirectResponse(url=f'/tasks?error=Ошибка: {e}', status_code=302)


@router.post('/tasks/{task_id}/edit')
async def task_edit(
    request: Request,
    task_id: int,
    title: str = Form(...),
    client_id: Optional[int] = Form(None),
    deadline: Optional[str] = Form(None),
    task_type: str = Form('custom'),
    priority: str = Form('medium'),
    notes: Optional[str] = Form(None),
    comment: Optional[str] = Form(None),
    status: str = Form('todo'),
    checklist_raw: Optional[str] = Form(None),
):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    try:
        dl = None
        if deadline:
            dl = parse_web_deadline(deadline)
        checklist = None
        if checklist_raw and checklist_raw.strip():
            try:
                checklist = json.loads(checklist_raw)
            except json.JSONDecodeError:
                pass

        async with async_session() as session:
            task = await session.get(Task, task_id)
            if task:
                task.title = title.strip()
                task.client_id = client_id if client_id else None
                task.deadline = to_utc(dl) if dl else None
                task.task_type = task_type
                task.priority = priority
                task.notes = notes
                task.comment = comment
                task.status = status
                if checklist is not None:
                    task.checklist = checklist
                await session.commit()
        return RedirectResponse(url=f'/tasks?success=Задача #{task_id} сохранена', status_code=302)
    except Exception as e:
        return RedirectResponse(url=f'/tasks?error=Ошибка: {e}', status_code=302)


@router.post('/tasks/{task_id}/done')
async def task_done(request: Request, task_id: int):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        ts = TaskService(session)
        await ts.mark_done(task_id)
    ref = request.headers.get('referer', '/tasks')
    return RedirectResponse(url=ref, status_code=302)


@router.post('/tasks/{task_id}/delete')
async def task_delete(request: Request, task_id: int):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        await session.execute(sa_delete(Reminder).where(Reminder.task_id == task_id))
        await session.execute(sa_delete(Task).where(Task.id == task_id))
        await session.commit()
    return RedirectResponse(url='/tasks', status_code=302)


@router.post('/tasks/{task_id}/snooze')
async def task_snooze(request: Request, task_id: int, new_deadline: str = Form(...)):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    dl = parse_web_deadline(new_deadline)
    if not dl:
        return RedirectResponse(url='/tasks?error=Не удалось распознать дату', status_code=302)
    async with async_session() as session:
        ts = TaskService(session)
        await ts.snooze(task_id, dl)
    return RedirectResponse(url=f'/tasks?success=Задача #{task_id} отложена', status_code=302)


# ─── API ──────────────────────────────────────────────────────

@router.get('/api/tasks')
async def api_tasks(start: str = '', end: str = ''):
    async with async_session() as session:
        ts = TaskService(session)
        all_tasks = await ts.list_tasks()
        tz = settings.tz
        now_local = datetime.now(tz)
        events = []
        for t in all_tasks:
            if not t.deadline:
                continue
            dl = safe_dt(t.deadline).astimezone(tz)
            if start and end:
                try:
                    s = datetime.fromisoformat(start)
                    e = datetime.fromisoformat(end)
                    if dl < s or dl > e:
                        continue
                except ValueError:
                    pass

            days_until = (dl - now_local).days
            if t.status == 'overdue' or days_until < 0:
                color = '#dc3545'
            elif days_until <= 2:
                color = '#ffc107'
            else:
                color = '#198754'

            if t.status == 'done':
                color = '#6c757d'

            client_name = t.client.org_name if t.client else ''
            notes = (t.notes[:100] + '...') if t.notes and len(t.notes) > 100 else (t.notes or '')
            checklist_progress = ''
            if t.checklist:
                done_items = sum(1 for ci in t.checklist if ci.get('done'))
                checklist_progress = f'{done_items}/{len(t.checklist)}'

            events.append({
                'id': str(t.id),
                'title': f'#{t.id} {t.title}',
                'start': dl.isoformat(),
                'end': dl.isoformat(),
                'color': color,
                'textColor': '#000' if color == '#ffc107' else '#fff',
                'status': t.status,
                'client': client_name,
                'priority': t.priority,
                'notes': notes,
                'checklist': checklist_progress,
                'task_type': t.task_type,
            })
            # Checklist items with reminders → separate calendar events
            if t.checklist:
                for ci_idx, ci in enumerate(t.checklist):
                    reminder_raw = ci.get('reminder')
                    if reminder_raw and not ci.get('done'):
                        try:
                            reminder_dt = datetime.fromisoformat(reminder_raw)
                            if start and end:
                                if reminder_dt < s or reminder_dt > e:
                                    continue
                            ci_color = '#0dcaf0'  # info/cyan
                            events.append({
                                'id': f'checklist-{t.id}-{ci_idx}',
                                'title': f'📌 {t.title} → {ci.get("text", "?")}',
                                'start': reminder_dt.isoformat(),
                                'end': reminder_dt.isoformat(),
                                'color': ci_color,
                                'textColor': '#000',
                                'status': t.status,
                                'client': client_name,
                                'priority': t.priority,
                                'notes': notes,
                                'checklist': '',
                                'task_type': t.task_type,
                                'task_id': t.id,
                                'is_checklist': True,
                                'checklist_idx': ci_idx,
                            })
                        except (ValueError, TypeError):
                            pass
    return JSONResponse(events)


@router.patch('/api/tasks/{task_id}')
async def api_task_update(task_id: str, request: Request):
    body = await request.json()
    # Check if this is a checklist reminder update
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
                    if 'deadline' in body and body['deadline']:
                        dl = parse_web_deadline(body['deadline'])
                        if dl:
                            checklist[ci_idx]['reminder'] = dl.isoformat()
                    task.checklist = checklist
                    await session.commit()
                return JSONResponse({'ok': True, 'id': task_id})

    real_task_id = int(task_id)
    async with async_session() as session:
        task = await session.get(Task, real_task_id)
        if not task:
            return JSONResponse({'error': 'Задача не найдена'}, status_code=404)

        if 'deadline' in body and body['deadline']:
            dl = parse_web_deadline(body['deadline'])
            if dl:
                task.deadline = to_utc(dl)
        if 'status' in body and body['status']:
            task.status = body['status']
        if 'notes' in body:
            task.notes = body['notes']
        if 'comment' in body:
            task.comment = body['comment']
        if 'checklist' in body and isinstance(body['checklist'], list):
            task.checklist = body['checklist']
        await session.commit()
    return JSONResponse({'ok': True, 'id': task_id})


@router.get('/api/tasks/all')
async def api_tasks_all():
    async with async_session() as session:
        ts = TaskService(session)
        all_tasks = await ts.list_tasks()
        tz = settings.tz
        now_local = datetime.now(tz)
        result = []
        for t in all_tasks:
            dl = safe_dt(t.deadline).astimezone(tz) if t.deadline else None
            client_name = t.client.org_name if t.client else ''
            result.append({
                'id': t.id,
                'title': t.title,
                'deadline': dl.isoformat() if dl else None,
                'status': t.status,
                'priority': t.priority,
                'task_type': t.task_type,
                'client': client_name,
                'notes': t.notes or '',
                'comment': t.comment or '',
                'checklist': t.checklist or [],
            })
        return JSONResponse(result)


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
        if 'text' in body and body['text']:
            checklist[idx]['text'] = body['text']
        if 'reminder' in body:
            if body['reminder']:
                checklist[idx]['reminder'] = body['reminder']
            else:
                checklist[idx].pop('reminder', None)

        task.checklist = checklist
        await session.commit()
        return JSONResponse({'ok': True, 'checklist': checklist})


@router.get('/api/clients')
async def api_clients():
    async with async_session() as session:
        cs = ClientService(session)
        clients = await cs.list_clients()
        return JSONResponse([{
            'id': c.id,
            'org_name': c.org_name,
            'domain': c.domain or '',
            'contract_end': format_datetime(c.contract_end, settings.tz) if c.contract_end else '',
        } for c in clients])


@router.get('/api/templates')
async def api_templates():
    return JSONResponse(CHECKLIST_TEMPLATES)


@router.post('/api/templates')
async def api_templates_save(request: Request):
    if not require_auth(request):
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

@router.get('/calendar')
async def calendar_page(request: Request):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        cs = ClientService(session)
        all_clients = await cs.list_clients()
    return templates.TemplateResponse('calendar.html', ctx(request,
        page='calendar',
        all_clients=all_clients,
        CHECKLIST_TEMPLATES=CHECKLIST_TEMPLATES,
        checklist_templates_json=json.dumps(CHECKLIST_TEMPLATES, ensure_ascii=False),
    ))


# ─── Clients ──────────────────────────────────────────────────

@router.get('/clients')
async def clients_page(
    request: Request,
    status_filter: str = '',
    search: str = '',
    sort: str = 'name',
    order: str = 'asc',
):
    if not require_auth(request):
        return RedirectResponse(url='/login')
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

    return templates.TemplateResponse('clients.html', ctx(request,
        clients=clients,
        status_filter=status_filter,
        search=search,
        sort=sort,
        order=order,
        page='clients',
    ))


@router.get('/clients/{client_id}')
async def client_detail(request: Request, client_id: int):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        cs = ClientService(session)
        ts = TaskService(session)
        client = await cs.get_client(client_id)
        if not client:
            return RedirectResponse(url='/clients?error=Клиент не найден')
        tasks = await ts.list_tasks(client_id=client_id)
        tz = settings.tz
        upcoming = [t for t in tasks if t.deadline and safe_dt(t.deadline) > utc_now() and t.status != 'done']
        upcoming.sort(key=lambda t: safe_dt(t.deadline))
        all_tasks_list = await ts.list_tasks()

    return templates.TemplateResponse('client_detail.html', ctx(request,
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
    domain: Optional[str] = Form(None),
    contract_end: str = Form(...),
    org_data: Optional[str] = Form(None),
):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    errors = []
    end = parse_web_deadline(contract_end)
    if not end:
        errors.append(f'Не удалось распознать дату окончания: {contract_end}')
    if errors:
        return RedirectResponse(url='/clients?error=' + '; '.join(errors), status_code=302)

    async with async_session() as session:
        cs = ClientService(session)
        await cs.create_client(
            org_name=org_name.strip(),
            domain=domain or None,
            contract_start=datetime.now(settings.tz),
            contract_end=end,
            org_data=org_data or None,
        )
    return RedirectResponse(url='/clients?success=Клиент создан', status_code=302)


@router.post('/clients/{client_id}/status')
async def client_status(request: Request, client_id: int, status: str = Form(...)):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        cs = ClientService(session)
        await cs.update_status(client_id, status)
    return RedirectResponse(url='/clients', status_code=302)


@router.post('/clients/{client_id}/update')
async def client_update(
    request: Request,
    client_id: int,
    org_name: str = Form(...),
    domain: Optional[str] = Form(None),
    contract_end: str = Form(...),
    org_data: Optional[str] = Form(None),
):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        client = await session.get(Client, client_id)
        if not client:
            return RedirectResponse(url='/clients?error=Клиент не найден')
        end = parse_web_deadline(contract_end)
        if end:
            client.org_name = org_name.strip()
            client.domain = domain or None
            client.contract_end = to_utc(end)
            client.org_data = org_data or None
            await session.commit()
    return RedirectResponse(url=f'/clients/{client_id}?success=Сохранено', status_code=302)


@router.post('/clients/{client_id}/delete')
async def client_delete(request: Request, client_id: int):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        await session.execute(sa_delete(Reminder).where(Reminder.client_id == client_id))
        await session.execute(sa_delete(Task).where(Task.client_id == client_id))
        await session.execute(sa_delete(Client).where(Client.id == client_id))
        await session.commit()
    return RedirectResponse(url='/clients', status_code=302)


# ─── Settings ─────────────────────────────────────────────────

@router.get('/settings')
async def settings_page(request: Request):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.id == 1))
        us = result.scalar_one_or_none()
        if not us:
            us = UserSettings(id=1, timezone=settings.DEFAULT_TIMEZONE, default_reminder_offset_hours=1)
            session.add(us)
            await session.commit()
    return templates.TemplateResponse('settings.html', ctx(request,
        settings=us,
        templates=CHECKLIST_TEMPLATES,
        page='settings',
    ))


@router.post('/settings')
async def settings_save(
    request: Request,
    timezone: str = Form(...),
    reminder_offset: int = Form(1),
):
    if not require_auth(request):
        return RedirectResponse(url='/login')
    async with async_session() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.id == 1))
        us = result.scalar_one_or_none()
        if not us:
            us = UserSettings(id=1)
            session.add(us)
        us.timezone = timezone
        us.default_reminder_offset_hours = reminder_offset
        us.last_sync = utc_now()
        await session.commit()
    settings.DEFAULT_TIMEZONE = timezone
    return RedirectResponse(url='/settings?success=Настройки сохранены', status_code=302)
