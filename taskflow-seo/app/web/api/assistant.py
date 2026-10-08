import json
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.core import ai_assistant as queue
from app.core.ai_security import redact_text, redact_value
from app.core.database import async_session
from app.core.models import AiRequest, AiQueueSettings, User
from app.core.permissions import get_current_user, require_root

router = APIRouter()


class Submit(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    kind: Literal['chat', 'task', 'report', 'polish'] = 'chat'
    conversation_id: UUID | None = None


class QueueSettings(BaseModel):
    paused: bool
    daily_limit: int = Field(ge=1, le=500)
    queue_limit: int = Field(ge=1, le=100)
    timeout_seconds: int = Field(ge=30, le=600)


async def job_payload(session, job, user=None, signature=None, allowed_sources=None):
    position = 0
    if job.status == 'queued':
        position = await session.scalar(select(func.count()).select_from(AiRequest).where(AiRequest.status == 'queued',
            (AiRequest.created_at < job.created_at) | ((AiRequest.created_at == job.created_at) & (AiRequest.id <= job.id))))
    visible = not user or not job.result or await queue.result_is_visible(job, user, signature, allowed_sources)
    return {'id': job.id, 'workspace_id': job.workspace_id, 'conversation_id': job.conversation_id, 'kind': job.kind, 'message': redact_text(job.message),
            'status': job.status, 'position': position, 'cancel_requested': job.cancel_requested,
            'created_at': job.created_at.isoformat() + 'Z', 'error': job.error if visible else 'Доступ к данным изменился. Начните новый диалог.',
            'result': redact_value(json.loads(job.result)) if job.result and visible else None}


async def owned_job(session, job_id, user, workspace_id, check_ai=True):
    job = await session.get(AiRequest, str(job_id))
    if not job or job.user_id != user.id or (workspace_id is not None and job.workspace_id != workspace_id):
        raise HTTPException(404, 'Запрос не найден')
    if check_ai:
        await queue.authorize(user, job.workspace_id)
    return job


async def assistant_user(workspace_id: int | None = Query(None), user=Depends(get_current_user)):
    await queue.authorize(user, workspace_id)
    return user


assistant_user._tf_guard = 'permission'


async def owned_request_user(job_id: UUID, workspace_id: int | None = Query(None), user=Depends(get_current_user)):
    async with async_session() as session:
        await owned_job(session, job_id, user, workspace_id, check_ai=False)
    return user


owned_request_user._tf_guard = 'permission'


@router.post('/api/assistant/requests', status_code=202)
async def submit(payload: Submit, workspace_id: int | None = Query(None), user=Depends(assistant_user)):
    message = payload.message.strip()
    if not message:
        raise HTTPException(400, 'Введите сообщение')
    job = await queue.enqueue(user, workspace_id, message, payload.kind, str(payload.conversation_id) if payload.conversation_id else None)
    async with async_session() as session:
        return await job_payload(session, job, user)


@router.get('/api/assistant/requests')
async def history(workspace_id: int | None = Query(None), user=Depends(assistant_user)):
    wid, _ = await queue.authorize(user, workspace_id)
    async with async_session() as session:
        jobs = (await session.scalars(select(AiRequest).where(AiRequest.user_id == user.id, AiRequest.workspace_id == wid)
            .order_by(AiRequest.created_at.desc(), AiRequest.id.desc()).limit(100))).all()
        signature = await queue.access_signature(user, wid)
        sources = await queue.visible_sources(user, wid, jobs)
        return [await job_payload(session, job, user, signature, sources) for job in reversed(jobs)]


@router.get('/api/assistant/active')
async def active(user=Depends(get_current_user)):
    # Only queue metadata; still available if AI rights were revoked during a request.
    async with async_session() as session:
        job = await session.scalar(select(AiRequest).where(AiRequest.user_id == user.id, AiRequest.status.in_(queue.ACTIVE)).limit(1))
        if not job:
            return None
        payload = await job_payload(session, job)
        payload.update(message='', result=None, error=None)
        return payload


@router.get('/api/assistant/requests/{job_id}')
async def status(job_id: UUID, workspace_id: int | None = Query(None), user=Depends(owned_request_user)):
    async with async_session() as session:
        return await job_payload(session, await owned_job(session, job_id, user, workspace_id), user)


@router.post('/api/assistant/requests/{job_id}/cancel')
async def cancel(job_id: UUID, workspace_id: int | None = Query(None), user=Depends(owned_request_user)):
    async with async_session() as session:
        job = await owned_job(session, job_id, user, workspace_id, check_ai=False)
        if job.status in queue.ACTIVE:
            job.cancel_requested = True
            if job.status == 'queued':
                job.status, job.finished_at = 'cancelled', queue.now()
            await session.commit()
        return await job_payload(session, job, user)


@router.delete('/api/assistant/history')
async def clear_history(workspace_id: int | None = Query(None), user=Depends(assistant_user)):
    wid, _ = await queue.authorize(user, workspace_id)
    async with async_session() as session:
        # Preserve usage accounting and limits while removing conversation contents.
        await session.execute(update(AiRequest).where(AiRequest.user_id == user.id, AiRequest.workspace_id == wid,
            AiRequest.status.in_(queue.TERMINAL)).values(message='', prepared_prompt=None, result=None, source_ids=None, conversation_id=AiRequest.id))
        await session.commit()
    return {'ok': True}


@router.get('/api/admin/ai')
async def admin(days: int = Query(7, ge=1, le=30), user=Depends(require_root())):
    await queue.initialize()
    async with async_session() as session:
        settings = await session.get(AiQueueSettings, 1)
        stats = (await session.execute(select(User.id, User.username, AiRequest.status, func.count(AiRequest.id),
            func.sum(AiRequest.input_tokens), func.sum(AiRequest.output_tokens), func.sum(AiRequest.duration_ms))
            .join(AiRequest, AiRequest.user_id == User.id).where(AiRequest.created_at >= queue.now() - timedelta(days=days))
            .group_by(User.id, User.username, AiRequest.status))).all()
        active = (await session.execute(select(AiRequest.id, User.username, AiRequest.workspace_id, AiRequest.kind, AiRequest.status, AiRequest.created_at)
            .join(User, User.id == AiRequest.user_id).where(AiRequest.status.in_(queue.ACTIVE)).order_by(AiRequest.created_at, AiRequest.id))).all()
        return {'settings': {key: getattr(settings, key) for key in QueueSettings.model_fields},
                'stats': [{'user_id': r[0], 'username': r[1], 'status': r[2], 'requests': r[3], 'input_tokens': r[4], 'output_tokens': r[5], 'duration_ms': r[6]} for r in stats],
                'queue': [{'id': r[0], 'username': r[1], 'workspace_id': r[2], 'kind': r[3], 'status': r[4], 'created_at': r[5].isoformat() + 'Z'} for r in active]}


@router.put('/api/admin/ai/settings')
async def configure(payload: QueueSettings, user=Depends(require_root())):
    await queue.initialize()
    async with async_session() as session:
        await session.execute(update(AiQueueSettings).where(AiQueueSettings.id == 1).values(**payload.model_dump()))
        await session.commit()
    return {'ok': True}


@router.post('/api/admin/ai/requests/{job_id}/cancel')
async def admin_cancel(job_id: UUID, user=Depends(require_root())):
    async with async_session() as session:
        job = await session.get(AiRequest, str(job_id))
        if not job:
            raise HTTPException(404, 'Запрос не найден')
        if job.status in queue.ACTIVE:
            job.cancel_requested = True
            if job.status == 'queued':
                job.status, job.finished_at = 'cancelled', queue.now()
            await session.commit()
    return {'ok': True}
