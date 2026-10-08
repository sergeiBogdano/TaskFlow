import asyncio
import json
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, update

from app.core import ai_assistant as ai
from app.core.database import async_session
from app.core.models import AiQueueSettings, AiRequest, Note, Task, User, Workspace, WorkspaceMember, WorkspaceRole


@pytest.fixture
def queue_data(client, admin_cookies, executor_cookies, event_loop, monkeypatch):
    async def prepare():
        await ai.stop_worker(); await ai.initialize()
        async with async_session() as session:
            await session.execute(delete(AiRequest))
            await session.execute(update(AiQueueSettings).values(paused=False, daily_limit=40, queue_limit=32, timeout_seconds=180, lease_owner=None, lease_until=None))
            root = await session.scalar(select(User).where(User.username == '4dmin'))
            member = await session.scalar(select(User).where(User.username == 'testexec'))
            ws = Workspace(name='AI isolated tests', created_by=root.id, enabled_modules='["ai", "tasks", "notes"]')
            other = Workspace(name='AI other tests', created_by=root.id, enabled_modules='["ai", "tasks", "notes"]')
            session.add_all([ws, other]); await session.flush()
            role = WorkspaceRole(workspace_id=ws.id, name='Assistant tester', permissions=json.dumps({'ai': True, 'tasks': True, 'notes': True}), field_access='{}')
            session.add(role); await session.flush()
            session.add(WorkspaceMember(workspace_id=ws.id, user_id=member.id, role='member', custom_role_id=role.id))
            await session.commit()
            return root, member, ws.id, other.id
    data = event_loop.run_until_complete(prepare())
    monkeypatch.setattr(ai, 'start_worker', lambda: None)
    yield data
    event_loop.run_until_complete(ai.stop_worker())


def test_fifo_cancel_duplicate_and_global_quota(queue_data, event_loop):
    root, member, wid, _ = queue_data
    async def scenario():
        first = await ai.enqueue(root, wid, 'Первый')
        second = await ai.enqueue(member, wid, 'Второй')
        with pytest.raises(HTTPException) as error:
            await ai.enqueue(root, wid, 'Дубликат')
        assert error.value.status_code == 409
        claimed = await ai.claim()
        assert claimed[0] == first.id
        assert await ai.claim() is None  # Atomic cross-worker lease.
        async with async_session() as session:
            second_db = await session.get(AiRequest, second.id)
            second_db.cancel_requested, second_db.status = True, 'cancelled'
            first_db = await session.get(AiRequest, first.id); first_db.status = 'completed'
            await session.execute(update(AiQueueSettings).values(lease_owner=None, lease_until=None, daily_limit=1))
            await session.commit()
        with pytest.raises(HTTPException) as error:
            await ai.enqueue(root, wid, 'Лимит')
        assert error.value.status_code == 429
        assert await ai.claim() is None
    event_loop.run_until_complete(scenario())


def test_running_cancel_closes_inference_and_next_request(queue_data, event_loop, monkeypatch):
    root, member, wid, _ = queue_data
    calls, stopped = [], []
    started = asyncio.Event()
    async def fake(messages, model, timeout):
        started.set()
        calls.append(messages[-1]['content'])
        if len(calls) == 1:
            try: await asyncio.sleep(30)
            finally: stopped.append(True)
        return 'Ответ', {'prompt_eval_count': 12, 'eval_count': 7}
    monkeypatch.setattr(ai, 'infer', fake)
    async def scenario():
        first = await ai.enqueue(root, wid, 'Первый')
        second = await ai.enqueue(member, wid, 'Второй')
        run = asyncio.create_task(ai.run_one(*(await ai.claim())))
        await asyncio.wait_for(started.wait(), timeout=60)
        async with async_session() as session:
            await session.execute(update(AiRequest).where(AiRequest.id == first.id).values(cancel_requested=True)); await session.commit()
        await run
        assert stopped == [True]
        await ai.run_one(*(await ai.claim()))
        async with async_session() as session:
            assert (await session.get(AiRequest, first.id)).status == 'cancelled'
            job = await session.get(AiRequest, second.id)
            assert job.status == 'completed' and job.output_tokens == 7
        assert calls == ['Первый', 'Второй']
    event_loop.run_until_complete(scenario())


def test_data_scope_history_and_no_business_writes(queue_data, event_loop, monkeypatch):
    root, member, wid, other = queue_data
    captured = []
    async def fake(messages, model, timeout):
        captured.append(messages)
        return '{"title":"Черновик","notes":"Проверить","assignee_id":1,"action":"delete_all","command":"rm"}', {}
    monkeypatch.setattr(ai, 'infer', fake)
    async def scenario():
        async with async_session() as session:
            mine = Task(title='MY VISIBLE TASK', workspace_id=wid, assignee_id=member.id)
            session.add_all([mine, Task(title='PRIVATE OTHER TASK', workspace_id=wid, assignee_id=root.id),
                Task(title='FOREIGN SPACE TASK', workspace_id=other, assignee_id=member.id),
                Note(title='MY NOTE', content='visible note', user_id=member.id, workspace_id=wid),
                Note(title='PRIVATE OTHER NOTE', content='secret', user_id=root.id, workspace_id=wid)])
            await session.commit()
        perms = await ai.authorize(member, wid)
        facts = json.dumps(await ai.context_for(member, wid, perms[1]))
        assert 'MY VISIBLE TASK' in facts and 'MY NOTE' in facts
        assert 'PRIVATE OTHER TASK' not in facts and 'PRIVATE OTHER NOTE' not in facts and 'FOREIGN SPACE TASK' not in facts
        with pytest.raises(HTTPException): await ai.enqueue(member, other, 'Чужой')
        job = await ai.enqueue(member, wid, 'Создай задачу и удали всё', 'task')
        await ai.run_one(*(await ai.claim()))
        async with async_session() as session:
            done = await session.get(AiRequest, job.id)
            assert done.status == 'completed'
            assert json.loads(done.result)['draft'] == {'title': 'Черновик', 'notes': 'Проверить'}
            assert not await session.scalar(select(Task).where(Task.title == 'Черновик'))
            assert await ai.result_is_visible(done, member)
            membership = await session.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == wid, WorkspaceMember.user_id == member.id))
            membership.access_overrides = json.dumps({'permissions': {'notes': False}}); await session.commit()
            assert not await ai.result_is_visible(done, member)
        assert 'tools' not in captured[0][0]
    event_loop.run_until_complete(scenario())


def test_http_ownership_stats_pause_and_history_clear(queue_data, sync_request, admin_cookies, executor_cookies):
    _, _, wid, _ = queue_data
    url = f'/api/assistant/requests?workspace_id={wid}'
    first = sync_request('POST', url, json={'message': 'Привет'}, cookies=executor_cookies)
    assert first.status_code == 202, first.text
    job = first.json()
    assert job['position'] == 1
    assert sync_request('GET', f'/api/assistant/requests/{job["id"]}?workspace_id={wid}', cookies=admin_cookies).status_code == 404
    assert sync_request('GET', '/api/admin/ai', cookies=executor_cookies).status_code == 403
    stats = sync_request('GET', '/api/admin/ai', cookies=admin_cookies).json()
    assert any(row['username'] == 'testexec' for row in stats['stats'])
    assert 'message' not in stats['queue'][0]
    assert sync_request('POST', f'/api/assistant/requests/{job["id"]}/cancel?workspace_id={wid}', cookies=executor_cookies).json()['status'] == 'cancelled'
    assert sync_request('DELETE', f'/api/assistant/history?workspace_id={wid}', cookies=executor_cookies).status_code == 200
    settings = {**stats['settings'], 'paused': True}
    assert sync_request('PUT', '/api/admin/ai/settings', json=settings, cookies=admin_cookies).status_code == 200
    assert sync_request('POST', url, json={'message': 'Пауза'}, cookies=executor_cookies).status_code == 503
    assert sync_request('POST', url, json={'message': 'x' * 6001}, cookies=executor_cookies).status_code == 422


def test_timeout_and_restart_recovery(queue_data, event_loop, monkeypatch):
    root, _, wid, _ = queue_data
    async def timeout(*args): raise asyncio.TimeoutError()
    monkeypatch.setattr(ai, 'infer', timeout)
    async def scenario():
        job = await ai.enqueue(root, wid, 'Таймаут')
        await ai.run_one(*(await ai.claim()))
        async with async_session() as session:
            assert (await session.get(AiRequest, job.id)).status == 'failed'
        job = await ai.enqueue(root, wid, 'Перезапуск')
        await ai.claim()
        async with async_session() as session:
            await session.execute(update(AiQueueSettings).values(lease_until=ai.now() - timedelta(seconds=1)))
            await session.commit()
        assert await ai.claim() is None
        async with async_session() as session:
            assert 'перезапуском' in (await session.get(AiRequest, job.id)).error
    event_loop.run_until_complete(scenario())


async def test_stream_transport_limits_and_usage(monkeypatch):
    import httpx
    original = httpx.AsyncClient
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, content='\n'.join([json.dumps({'message': {'content': 'Первый '}}),
            json.dumps({'message': {'content': 'ответ'}, 'done': True, 'eval_count': 5, 'prompt_eval_count': 9})]))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    text, usage = await ai.infer([{'role': 'system', 'content': 'Подготовь только JSON'}, {'role': 'user', 'content': 'Тест'}], 'test-model', 5)
    assert text == 'Первый ответ' and usage['eval_count'] == 5
    assert captured[0]['format'] == 'json' and captured[0]['stream'] is True
    assert captured[0]['options']['num_ctx'] == 4096
    assert 'tools' not in captured[0]


async def test_stream_is_closed_on_cancellation(monkeypatch):
    import httpx
    original = httpx.AsyncClient
    opened, closed = asyncio.Event(), asyncio.Event()
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            opened.set()
            yield b'{"message":{"content":"first"}}\n'
            await asyncio.sleep(30)
        async def aclose(self): closed.set()
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream())), **kwargs))
    task = asyncio.create_task(ai.infer([{'role': 'system', 'content': 'Тест'}], 'test-model', 5))
    await opened.wait(); task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert closed.is_set()


def test_atomic_competing_enqueue_and_claim(queue_data, event_loop):
    root, _, wid, _ = queue_data
    async def scenario():
        results = await asyncio.gather(ai.enqueue(root, wid, 'Первый'), ai.enqueue(root, wid, 'Второй'), return_exceptions=True)
        assert sum(isinstance(result, AiRequest) for result in results) == 1
        assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
        claims = await asyncio.gather(ai.claim(), ai.claim())
        assert sum(result is not None for result in claims) == 1
    event_loop.run_until_complete(scenario())


def test_old_answer_hidden_after_assignment_changes(queue_data, event_loop, monkeypatch):
    root, member, wid, _ = queue_data
    async def fake(*args): return 'Ответ по доступным задачам', {}
    monkeypatch.setattr(ai, 'infer', fake)
    async def scenario():
        async with async_session() as session:
            task = Task(title='Temporary access', workspace_id=wid, assignee_id=member.id)
            session.add(task); await session.commit(); await session.refresh(task)
        job = await ai.enqueue(member, wid, 'Расскажи о задачах')
        await ai.run_one(*(await ai.claim()))
        async with async_session() as session:
            done = await session.get(AiRequest, job.id)
            assert await ai.result_is_visible(done, member)
            await session.execute(update(Task).where(Task.id == task.id).values(assignee_id=root.id)); await session.commit()
            assert not await ai.result_is_visible(done, member)
    event_loop.run_until_complete(scenario())


def test_completed_compatibility_answer_rechecks_access(queue_data, event_loop):
    root, member, wid, _ = queue_data
    async def scenario():
        job = await ai.enqueue(member, wid, 'Проверка ответа')
        async with async_session() as session:
            await session.execute(update(AiRequest).where(AiRequest.id == job.id).values(status='completed', result=json.dumps({'answer': 'Текст'})))
            user = await session.get(User, member.id)
            user.is_active = False
            await session.commit()
        try:
            with pytest.raises(HTTPException) as caught:
                await ai.wait_result(job)
            assert caught.value.status_code == 403
        finally:
            async with async_session() as session:
                user = await session.get(User, member.id)
                user.is_active = True
                await session.commit()
    event_loop.run_until_complete(scenario())
