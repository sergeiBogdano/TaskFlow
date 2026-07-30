from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import QuickTaskTemplate
from app.core.permissions import get_current_user

router = APIRouter(prefix="/api/quick-tasks", tags=["quick-tasks"])


def _template_to_dict(template: QuickTaskTemplate) -> dict:
    return {
        'id': template.id,
        'title': template.title,
        'task_type': template.task_type,
        'priority': template.priority,
    }


@router.get('')
async def list_quick_tasks(user=Depends(get_current_user)):
    async with async_session() as session:
        templates = (await session.execute(
            select(QuickTaskTemplate).order_by(QuickTaskTemplate.id)
        )).scalars().all()
        if not templates:
            for title in ['Позвонить клиенту', 'Проверить оплату', 'Запросить доступы']:
                session.add(QuickTaskTemplate(title=title))
            await session.commit()
            templates = (await session.execute(
                select(QuickTaskTemplate).order_by(QuickTaskTemplate.id)
            )).scalars().all()
    return JSONResponse([_template_to_dict(template) for template in templates])


@router.post('')
async def create_quick_task(data: dict, user=Depends(get_current_user)):
    title = (data.get('title') or '').strip()
    if not title:
        raise HTTPException(status_code=400, detail='Title is required')
    async with async_session() as session:
        template = QuickTaskTemplate(
            title=title,
            task_type=data.get('task_type') or 'custom',
            priority=data.get('priority') or 'medium',
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
    return JSONResponse(_template_to_dict(template), status_code=201)


@router.delete('/{template_id}')
async def delete_quick_task(template_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        template = await session.get(QuickTaskTemplate, template_id)
        if template:
            await session.delete(template)
            await session.commit()
    return JSONResponse({'ok': True})
