from __future__ import annotations

import asyncio

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.auth import COOKIE_NAME, hash_password, verify_password, verify_session_token
from app.core.database import async_session
from app.core.models import User
from app.core.sse import register_queue, unregister_queue
from app.services.user_service import get_user
from app.web.templates_setup import templates

router = APIRouter()


async def _current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = verify_session_token(token)
    if user_id is None:
        return None
    return await get_user(user_id)


# ─── SSE ────────────────────────────────────────────────────

@router.get('/api/sse')
async def api_sse(request: Request):
    user = await _current_user(request)
    if not user:
        return JSONResponse({'error': 'auth'}, status_code=401)
    once = request.query_params.get('once') == '1'
    q = await register_queue(user.id)

    async def event_stream():
        try:
            yield 'event: ready\ndata: {}\n\n'
            if once:
                return
            while True:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=30)
                    yield f'event: {event}\ndata: {data}\n\n'
                except TimeoutError:
                    yield ': keepalive\n\n'
        except asyncio.CancelledError:
            pass
        finally:
            await unregister_queue(user.id, q)

    return StreamingResponse(event_stream(), media_type='text/event-stream')


# ─── Password Change ────────────────────────────────────────

@router.post('/api/users/change-password')
async def api_change_password(request: Request, current_password: str = Form(''), new_password: str = Form('')):
    user = await _current_user(request)
    if not user:
        return JSONResponse({'error': 'auth'}, status_code=401)
    if not verify_password(current_password, user.password_hash):
        return JSONResponse({'error': 'Неверный текущий пароль'}, status_code=400)
    if not new_password or len(new_password) < 4:
        return JSONResponse({'error': 'Новый пароль должен быть минимум 4 символа'}, status_code=400)
    async with async_session() as session:
        u = await session.get(User, user.id)
        if u:
            u.password_hash = hash_password(new_password)
            await session.commit()
    return JSONResponse({'ok': True})


def ctx(request: Request, **kw) -> dict:
    from app.web.router import ctx as main_ctx
    return main_ctx(request, **kw)
