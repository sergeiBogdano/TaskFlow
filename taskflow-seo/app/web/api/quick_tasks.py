from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import QuickTaskTemplate
from app.core.permissions import get_current_user, get_user_role_names, resolve_workspace

router = APIRouter(prefix="/api/quick-tasks", tags=["quick-tasks"])


def _template_to_dict(template: QuickTaskTemplate) -> dict:
    return {
        'id': template.id,
        'title': template.title,
        'task_type': template.task_type,
        'priority': template.priority,
    }


@router.get('')
async def list_quick_tasks(workspace_id: int | None = Query(None), user=Depends(get_current_user)):
    async with async_session() as session:
        roles = await get_user_role_names(user.id)
        workspace, _ = await resolve_workspace(session, user, roles, workspace_id)
        templates = (await session.execute(
            select(QuickTaskTemplate).where(
                QuickTaskTemplate.workspace_id == workspace.id
            ).order_by(QuickTaskTemplate.id)
        )).scalars().all()
        if not templates:
            for title in ['Позвонить клиенту', 'Проверить оплату', 'Запросить доступы']:
                session.add(QuickTaskTemplate(title=title, workspace_id=workspace.id))
            await session.commit()
            templates = (await session.execute(
                select(QuickTaskTemplate).where(
                    QuickTaskTemplate.workspace_id == workspace.id
                ).order_by(QuickTaskTemplate.id)
            )).scalars().all()
    return JSONResponse([_template_to_dict(template) for template in templates])


@router.post('')
async def create_quick_task(data: dict, workspace_id: int | None = Query(None), user=Depends(get_current_user)):
    title = (data.get('title') or '').strip()
    if not title:
        raise HTTPException(status_code=400, detail='Title is required')
    async with async_session() as session:
        roles = await get_user_role_names(user.id)
        workspace, _ = await resolve_workspace(session, user, roles, workspace_id)
        template = QuickTaskTemplate(
            workspace_id=workspace.id,
            title=title,
            task_type=data.get('task_type') or 'custom',
            priority=data.get('priority') or 'medium',
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
    return JSONResponse(_template_to_dict(template), status_code=201)


@router.delete('/{template_id}')
async def delete_quick_task(template_id: int, workspace_id: int | None = Query(None), user=Depends(get_current_user)):
    async with async_session() as session:
        roles = await get_user_role_names(user.id)
        workspace, _ = await resolve_workspace(session, user, roles, workspace_id)
        template = (await session.execute(select(QuickTaskTemplate).where(
            QuickTaskTemplate.id == template_id,
            QuickTaskTemplate.workspace_id == workspace.id,
        ))).scalar_one_or_none()
        if template:
            await session.delete(template)
            await session.commit()
    return JSONResponse({'ok': True})
