"""Compatibility endpoints; all inference goes through the assistant queue."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core import ai_assistant as ai
from app.core.permissions import get_current_user
from app.core.rich_text import clean_html

router = APIRouter(prefix='/api/ai')


class TaskCommandPayload(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    draft: dict | None = None
    model: str | None = None


class TextPolishPayload(BaseModel):
    text: str = Field(max_length=6000)
    model: str | None = None


@router.post('/task-command')
async def parse_task_command(payload: TaskCommandPayload, workspace_id: int | None = Query(None), user=Depends(get_current_user)):
    job = await ai.enqueue(user, workspace_id, payload.text.strip(), 'task')
    try:
        result, _ = await ai.wait_result(job)
    except HTTPException:
        raise
    except Exception:
        return JSONResponse({'error': 'Помощник недоступен. Повторите запрос позднее.'}, status_code=503)
    return {'draft': result.get('draft') or {}, 'missing': [], 'questions': [], 'clients': [], 'users': []}


@router.post('/text-polish')
async def polish_text(payload: TextPolishPayload, workspace_id: int | None = Query(None), user=Depends(get_current_user)):
    if not payload.text.strip():
        return {'html': ''}
    job = await ai.enqueue(user, workspace_id, payload.text, 'polish')
    try:
        result, _ = await ai.wait_result(job)
    except HTTPException:
        raise
    except Exception:
        return JSONResponse({'error': 'Помощник недоступен. Повторите запрос позднее.'}, status_code=503)
    return {'html': clean_html(result['answer'])}
