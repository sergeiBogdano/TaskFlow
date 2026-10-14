import pytest
import json
from datetime import datetime, timedelta

from sqlalchemy import select
from app.core.config import settings
from app.core.database import async_session
from app.core.models import Task, User, Workspace, WorkspaceMember, WorkspaceRole
from app.core.utils.timezone import to_utc


def test_dashboard_and_overdue_filter_match_without_status_worker(client, admin_cookies, executor_cookies, sync_request, event_loop):
    async def prepare():
        async with async_session() as session:
            root = await session.scalar(select(User).where(User.username == '4dmin'))
            executor = await session.scalar(select(User).where(User.username == 'testexec'))
            ws = Workspace(name='Overdue consistency', created_by=root.id)
            foreign = Workspace(name='Foreign overdue', created_by=root.id)
            session.add_all([ws, foreign]); await session.flush()
            role = WorkspaceRole(workspace_id=ws.id, name='Task reader', permissions=json.dumps({'tasks': True, 'dashboard': True}), field_access='{}')
            session.add(role); await session.flush()
            session.add(WorkspaceMember(workspace_id=ws.id, user_id=executor.id, role='member', custom_role_id=role.id))
            today = to_utc(datetime.now(settings.tz).replace(hour=0, minute=0, second=0, microsecond=0))
            past, future = today - timedelta(days=1), today + timedelta(days=1)
            rows = [
                Task(title='Date-derived overdue', status='todo', deadline=past, workspace_id=ws.id, assignee_id=executor.id),
                Task(title='Completed late', status='done', deadline=past, workspace_id=ws.id, assignee_id=executor.id),
                Task(title='Due today', status='todo', deadline=today, workspace_id=ws.id, assignee_id=executor.id),
                Task(title='Explicit overdue', status='overdue', deadline=future, workspace_id=ws.id, assignee_id=executor.id),
                Task(title='Planned date elapsed', status='waiting', completion_date=past, deadline=future, workspace_id=ws.id, assignee_id=executor.id),
                Task(title='No date', status='todo', workspace_id=ws.id, assignee_id=executor.id),
                Task(title='Deleted overdue', status='todo', deadline=past, deleted_at=today, workspace_id=ws.id),
                Task(title='Foreign overdue', status='todo', deadline=past, workspace_id=foreign.id),
            ]
            session.add_all(rows); await session.flush()
            expected = {rows[index].id for index in (0, 3, 4)}
            await session.commit()
            return ws.id, expected, rows[1].id
    wid, expected, done_id = event_loop.run_until_complete(prepare())
    stats = sync_request('GET', f'/api/dashboard/stats?workspace_id={wid}', cookies=admin_cookies)
    assert stats.status_code == 200, stats.text
    assert stats.json()['overdue'] == 3 and stats.json()['task_scope'] == 'all'
    member_stats = sync_request('GET', f'/api/dashboard/stats?workspace_id={wid}', cookies=executor_cookies)
    assert member_stats.status_code == 200, member_stats.text
    assert member_stats.json()['task_scope'] == 'involved' and member_stats.json()['overdue'] == 3
    member_list = sync_request('GET', f'/api/tasks?workspace_id={wid}&scope=involved&status=overdue', cookies=executor_cookies)
    assert member_list.status_code == 200, member_list.text
    assert {row['id'] for row in member_list.json()} == expected
    url = f'/api/tasks?workspace_id={wid}&scope=all&status=overdue'
    listing = sync_request('GET', url, cookies=admin_cookies)
    assert listing.status_code == 200, listing.text
    assert {row['id'] for row in listing.json()} == expected
    page = sync_request('GET', url + '&paginated=true&page_size=1', cookies=admin_cookies).json()
    assert page['total'] == 3 and len(page['items']) == 1
    assert page['status_counts']['overdue'] == 3 and page['status_counts']['done'] == 1
    mixed = sync_request('GET', url.replace('status=overdue', 'status=done,overdue'), cookies=admin_cookies).json()
    assert {row['id'] for row in mixed} == expected | {done_id}
    assert {row['status'] for row in listing.json()} == {'todo', 'waiting', 'overdue'}
    # Closing an overdue task updates the dashboard immediately, without a cache delay.
    async def close():
        async with async_session() as session:
            task = await session.get(Task, min(expected)); task.status = 'done'; await session.commit()
    event_loop.run_until_complete(close())
    fresh = sync_request('GET', f'/api/dashboard/stats?workspace_id={wid}', cookies=admin_cookies).json()
    assert fresh['overdue'] == 2


@pytest.mark.parametrize('hidden', ['deadline', 'completionDate'])
def test_hidden_dates_block_overdue_filter_and_aggregate(client, admin_cookies, executor_cookies, sync_request, event_loop, hidden):
    async def prepare():
        async with async_session() as session:
            root = await session.scalar(select(User).where(User.username == '4dmin'))
            member = await session.scalar(select(User).where(User.username == 'testexec'))
            ws = Workspace(name='Hidden date privacy', created_by=root.id)
            session.add(ws); await session.flush()
            role = WorkspaceRole(workspace_id=ws.id, name='Hidden date reader', permissions=json.dumps({'tasks': True}), field_access=json.dumps({'tasks': {hidden: 'hidden', 'assignee': 'hidden'}}))
            session.add(role); await session.flush()
            session.add(WorkspaceMember(workspace_id=ws.id, user_id=member.id, role='member', custom_role_id=role.id))
            past = to_utc(datetime.now(settings.tz)) - timedelta(days=2)
            task = Task(title='Authorized but redacted', assignee_id=member.id, workspace_id=ws.id, status='todo', deadline=past, completion_date=past)
            session.add(task); await session.flush(); ident = task.id
            await session.commit(); return ws.id, ident
    wid, ident = event_loop.run_until_complete(prepare())
    for status in ['overdue', 'done,overdue', 'todo, overdue']:
        r = sync_request('GET', f'/api/tasks?workspace_id={wid}&scope=mine&status={status}', cookies=executor_cookies)
        assert r.status_code == 403, r.text
    r = sync_request('GET', f'/api/tasks?workspace_id={wid}&scope=mine&paginated=true', cookies=executor_cookies)
    assert r.status_code == 200, r.text
    assert r.json()['total'] == 1 and r.json()['items'][0]['id'] == ident
    assert 'assignee_id' not in r.json()['items'][0]
    assert 'overdue' not in r.json()['status_counts']
    assert ('deadline' if hidden == 'deadline' else 'completion_date') not in r.json()['items'][0]


def test_calendar_today_not_overdue(client, admin_cookies, sync_request, event_loop, monkeypatch):
    from app.web.api import calendar
    fixed = datetime.now(settings.tz).replace(hour=12, minute=0, second=0, microsecond=0)
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(calendar, 'datetime', FrozenDateTime)
    async def prepare():
        async with async_session() as session:
            root = await session.scalar(select(User).where(User.username == '4dmin'))
            ws = Workspace(name='Calendar days', created_by=root.id)
            session.add(ws); await session.flush()
            for title, offset, status in [('Today', 0, 'todo'), ('Yesterday', -1, 'todo'), ('Tomorrow', 1, 'todo'), ('Done', -1, 'done')]:
                day = fixed.replace(hour=18) + timedelta(days=offset)
                session.add(Task(title=title, workspace_id=ws.id, status=status, completion_date=to_utc(day), deadline=to_utc(day + timedelta(days=1))))
            await session.commit(); return ws.id
    wid = event_loop.run_until_complete(prepare())
    r = sync_request('GET', f'/api/calendar?workspace_id={wid}&scope=all', cookies=admin_cookies)
    assert r.status_code == 200, r.text
    colors = {row['title']: row['color'] for row in r.json()}
    assert colors == {'Today': '#ffc107', 'Yesterday': '#dc3545', 'Tomorrow': '#ffc107'}
    assert 'Done' not in colors  # Completed tasks are intentionally excluded from this calendar.
