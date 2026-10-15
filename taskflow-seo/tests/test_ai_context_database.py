"""Real SQL for bounded assistant retrieval/provenance on both supported databases."""
import json
from types import SimpleNamespace

from app.core import ai_assistant as ai
from app.core.access_policy import FIELD_CATALOG
from app.core.models import Note, Task, User, Workspace
from tests.test_user_deletion import deletion_db


async def test_note_folder_move_trash_restore_and_permissions_update_assistant_context(deletion_db, monkeypatch):
    from app.core.models import NoteFolder
    from app.core.utils.timezone import utc_now
    permissions = {'notes': True}
    async def fields(*args): return {}
    async def features(*args): return True
    async def effective(*args): return permissions
    monkeypatch.setattr(ai, 'async_session', deletion_db)
    monkeypatch.setattr(ai, 'field_access', fields)
    monkeypatch.setattr(ai, 'is_feature_available', features)
    monkeypatch.setattr(ai, 'effective_permissions', effective)
    async with deletion_db() as session:
        owner = User(username='note-transfer-owner', password_hash='unused')
        other = User(username='note-transfer-other', password_hash='unused')
        session.add_all([owner, other]); await session.flush()
        ws = Workspace(name='Notes context', created_by=owner.id)
        foreign = Workspace(name='Other context', created_by=owner.id)
        session.add_all([ws, foreign]); await session.flush()
        folder = NoteFolder(name='Moved notes', user_id=owner.id)
        session.add(folder); await session.flush()
        note = Note(title='Transferneedle own note', content='```sh\nnever execute this text\n```', user_id=owner.id, workspace_id=ws.id, folder_id=None)
        session.add_all([note, Note(title='Transferneedle private foreign owner', content='PRIVATE_PAYLOAD', user_id=other.id, workspace_id=ws.id), Note(title='Transferneedle other workspace', content='FOREIGN_PAYLOAD', user_id=owner.id, workspace_id=foreign.id)])
        await session.commit(); wid, nid, fid = ws.id, note.id, folder.id
    async def current():
        return await ai.context_for(owner, wid, permissions, 'Проанализируй заметку Transferneedle')
    facts = await current()
    assert [n['id'] for n in facts['notes']] == [nid]
    assert 'PRIVATE_PAYLOAD' not in json.dumps(facts) and 'FOREIGN_PAYLOAD' not in json.dumps(facts)
    async with deletion_db() as session:
        note = await session.get(Note, nid); note.folder_id = fid; await session.commit()
    assert [n['id'] for n in (await current())['notes']] == [nid]
    async with deletion_db() as session:
        note = await session.get(Note, nid); note.deleted_at = utc_now(); await session.commit()
    assert not (await current()).get('notes')
    async with deletion_db() as session:
        note = await session.get(Note, nid); note.deleted_at = None; await session.commit()
    assert [n['id'] for n in (await current())['notes']] == [nid]
    permissions['notes'] = False
    assert not (await current()).get('notes')


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


async def test_period_filters_before_sampling_and_counts(deletion_db, monkeypatch):
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    from app.core.models import Client, Contract, Sprint
    permissions = {'tasks': True, 'notes': True, 'clients': True, 'client_tab_contracts': True, 'kanban': True}
    async def fields(*args): return {entity: {key: 'edit' for key in keys} for entity, keys in FIELD_CATALOG.items()}
    async def features(*args): return True
    monkeypatch.setattr(ai, 'async_session', deletion_db)
    monkeypatch.setattr(ai, 'field_access', fields)
    monkeypatch.setattr(ai, 'is_feature_available', features)
    monkeypatch.setattr(ai, 'app_settings', SimpleNamespace(tz=ZoneInfo('Europe/Moscow')))
    async with deletion_db() as session:
        user = User(username='period-reader', password_hash='unused'); session.add(user); await session.flush()
        ws = Workspace(name='period database', created_by=user.id); session.add(ws); await session.flush()
        # The upper bound is exclusive: Jan 31 21:00 UTC = Feb 1 00:00 Moscow.
        session.add_all([Task(title='Inside last second', workspace_id=ws.id, assignee_id=user.id, created_at=datetime(2026, 1, 31, 20, 59, 59)),
                         Task(title='Outside next midnight', workspace_id=ws.id, assignee_id=user.id, created_at=datetime(2026, 1, 31, 21)),
                         Task(title='Outside old', workspace_id=ws.id, assignee_id=user.id, created_at=datetime(2025, 12, 1)),
                         Task(title='Updated inside', workspace_id=ws.id, assignee_id=user.id, created_at=datetime(2025, 12, 1), updated_at=datetime(2026, 1, 15)),
                         Note(title='Outside note', content='Excluded', user_id=user.id, workspace_id=ws.id, created_at=datetime(2025, 12, 1)),
                         Note(title='Inside note', content='Allowed', user_id=user.id, workspace_id=ws.id, created_at=datetime(2026, 1, 15)),
                         Sprint(name='Outside sprint', workspace_id=ws.id, created_at=datetime(2025, 12, 1))])
        client = Client(org_name='Outside client', workspace_id=ws.id, created_at=datetime(2025, 12, 1), contract_start=datetime(2025, 1, 1), contract_end=datetime(2027, 1, 1))
        session.add(client); await session.flush()
        session.add_all([Contract(client_id=client.id, contract_type='Overlapping contract', start_date=datetime(2025, 1, 1), end_date=datetime(2027, 1, 1)),
                         Contract(client_id=client.id, contract_type='Outside contract', start_date=datetime(2027, 1, 1), end_date=datetime(2027, 12, 1))])
        await session.commit(); wid = ws.id
    context = await ai.context_for(user, wid, permissions, 'Outside', date(2026, 1, 1), date(2026, 1, 31))
    assert context['tasks']['total_visible'] == 2
    assert {item['title'] for item in context['tasks']['items']} == {'Inside last second', 'Updated inside'}
    assert [note['title'] for note in context['notes']] == ['Inside note']
    assert context['organizations'] == [] and context['sprints'] == []
    assert [contract['type'] for contract in context['contracts']] == ['Overlapping contract']
    assert context['period']['days'] == 31


async def test_period_columns_migrate_existing_queue(deletion_db, monkeypatch):
    from sqlalchemy import text
    from app.core import database
    from app.core.models import AiRequest
    engine = deletion_db.kw['bind']
    async with deletion_db() as session:
        user = User(username='queue-migration', password_hash='unused'); session.add(user); await session.flush()
        workspace = Workspace(name='Existing queue', created_by=user.id); session.add(workspace); await session.flush()
        job = AiRequest(user_id=user.id, workspace_id=workspace.id, conversation_id='migration', message='Keep old message', status='completed')
        session.add(job); await session.commit(); job_id = job.id
    async with engine.begin() as connection:
        await connection.execute(text('ALTER TABLE ai_requests DROP COLUMN date_start'))
        await connection.execute(text('ALTER TABLE ai_requests DROP COLUMN date_end'))
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'settings', SimpleNamespace(DATABASE_URL=str(engine.url)))
    await database._migrate()
    await database._ensure_indexes()
    async with deletion_db() as session:
        job = await session.get(AiRequest, job_id)
        assert job.message == 'Keep old message'
        assert job.date_start is None and job.date_end is None
