from __future__ import annotations

import asyncio
import json

_user_queues: dict[int, list[asyncio.Queue]] = {}
_lock = asyncio.Lock()


async def register_queue(user_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    async with _lock:
        _user_queues.setdefault(user_id, []).append(q)
    return q


async def unregister_queue(user_id: int, q: asyncio.Queue):
    async with _lock:
        queues = _user_queues.get(user_id, [])
        if q in queues:
            queues.remove(q)


async def send_sse(user_id: int, event: str, data: dict):
    async with _lock:
        queues = _user_queues.get(user_id, [])
        for q in queues:
            await q.put((event, json.dumps(data, ensure_ascii=False, default=str)))


async def send_sse_all(event: str, data: dict):
    async with _lock:
        for queues in _user_queues.values():
            for q in queues:
                await q.put((event, json.dumps(data, ensure_ascii=False, default=str)))
