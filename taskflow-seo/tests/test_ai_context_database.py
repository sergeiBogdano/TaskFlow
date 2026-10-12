"""Real SQL for bounded assistant retrieval/provenance on both supported databases."""
import json
from types import SimpleNamespace

from app.core import ai_assistant as ai
from app.core.access_policy import FIELD_CATALOG
from app.core.models import Note, Task, User, Workspace
from tests.test_user_deletion import deletion_db


async def test_bounded_context_and_chunked_provenance(deletion_db, monkeypatch):
    permissions = {'tasks': True, 'notes': True}
    async def fields(*args):
        return {entity: {key: 'edit' for key in keys} for entity, keys in FIELD_CATALOG.items()}
    async def features(*args): return True
    async def effective(*args): return permissions
    monkeypatch.setattr(ai, 'async_session', deletion_db)
    monkeypatch.setattr(ai, 'field_access', fields)
    monkeypatch.setattr(ai, 'is_feature_available', features)
    monkeypatch.setattr(ai, 'effective_permissions', effective)
    async with deletion_db() as session:
        user = User(username='bounded-reader', password_hash='unused')
        other = User(username='outside-reader', password_hash='unused')
        session.add_all([user, other]); await session.flush()
        ws = Workspace(name='bounded', created_by=user.id)
        foreign = Workspace(name='foreign', created_by=other.id)
        session.add_all([ws, foreign]); await session.flush()
        old = Task(title='Rarequartz older match', assignee_id=user.id, workspace_id=ws.id)
        session.add(old); await session.flush(); old_id = old.id
        session.add_all([Task(title=f'Fresh {index}', assignee_id=user.id, workspace_id=ws.id) for index in range(1001)])
        session.add_all([Task(title='Rarequartz foreign', assignee_id=user.id, workspace_id=foreign.id),
                         Task(title='Rarequartz private', assignee_id=other.id, workspace_id=ws.id),
                         Note(title='Requested notebook', content='Padding ' * 200 + 'Rarequartz requested fragment', user_id=user.id, workspace_id=ws.id)])
        await session.commit(); wid = ws.id
    facts = await ai.context_for(user, wid, permissions, 'Найди задачу Rarequartz')
    assert facts['tasks']['items'][0]['id'] == old_id
    assert facts['tasks']['total_visible'] == 1000
    assert facts['tasks']['totals_complete'] is False
    assert 'Rarequartz requested fragment' in facts['notes'][0]['content']
    assert 'private' not in json.dumps(facts) and 'foreign' not in json.dumps(facts)
    # Aggregate rows AND individually selected older sources are tracked.
    source_ids = set(facts['_source_ids']['tasks']) | {row['id'] for row in facts['tasks']['items']}
    jobs = [SimpleNamespace(source_ids=json.dumps({'tasks': sorted(source_ids)}))]
    visible = await ai.visible_sources(user, wid, jobs)
    assert visible['tasks'] == source_ids
    async with deletion_db() as session:
        task = await session.get(Task, old_id); task.assignee_id = other.id
        await session.commit()
    assert old_id not in (await ai.visible_sources(user, wid, jobs))['tasks']


async def test_dashboard_chart_timezone_bucketing(deletion_db, monkeypatch):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from app.web.api import dashboard
    from app.core.cache import dashboard_cache
    async with deletion_db() as session:
        user = User(username='chart-reader', password_hash='unused')
        session.add(user); await session.flush()
        ws = Workspace(name='Chart boundary', created_by=user.id)
        foreign = Workspace(name='Other chart', created_by=user.id)
        session.add_all([ws, foreign]); await session.flush()
        # 22:00 UTC belongs to the next day in Moscow.
        stamp = datetime(2026, 10, 11, 22)
        session.add_all([Task(title='Boundary', workspace_id=ws.id, status='done', created_at=stamp, updated_at=stamp),
                         Task(title='Excluded foreign', workspace_id=foreign.id, status='done', created_at=stamp, updated_at=stamp)])
        await session.commit(); wid = ws.id
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 12, 12, tzinfo=timezone.utc).astimezone(tz)
    async def roles(*args): return {'superadmin'}
    async def resolve(*args): return SimpleNamespace(id=wid), 'owner'
    monkeypatch.setattr(dashboard, 'async_session', deletion_db)
    monkeypatch.setattr(dashboard, 'datetime', FixedDatetime)
    monkeypatch.setattr(dashboard, 'settings', SimpleNamespace(tz=ZoneInfo('Europe/Moscow')))
    monkeypatch.setattr(dashboard, 'get_user_role_names', roles)
    monkeypatch.setattr(dashboard, 'resolve_workspace', resolve)
    dashboard_cache.clear()
    response = await dashboard.dashboard_chart('week', wid, user)
    payload = json.loads(response.body)
    assert len(payload['labels']) == 7 and payload['labels'][-1] == '12.10'
    assert payload['created'] == [0, 0, 0, 0, 0, 0, 1]
    assert payload['done'] == [0, 0, 0, 0, 0, 0, 1]
    dashboard_cache.clear()
