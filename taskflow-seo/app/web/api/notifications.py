from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.database import async_session
from app.core.models import UserSettings
from app.core.permissions import get_current_user
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get('')
async def list_notifications(unread_only: bool = False, limit: int = 100, user=Depends(get_current_user)):
    async with async_session() as session:
        ns = NotificationService(session)
        notifications = await ns.list_notifications(unread_only=unread_only, limit=limit, user_id=user.id)
        unread_count = await ns.get_unread_count(user_id=user.id)
    return JSONResponse({
        'unread_count': unread_count,
        'notifications': [{
            'id': n.id,
            'type': n.notification_type,
            'title': n.title,
            'task_id': n.task_id,
            'client_id': n.client_id,
            'notification_type': n.notification_type,
            'message': n.message or '',
            'read': n.read,
            'is_read': n.read,
            'created_at': n.created_at.isoformat() if n.created_at else '',
            'task_title': n.task.title if n.task else None,
        } for n in notifications],
    })


@router.post('/{notif_id}/read')
async def mark_read(notif_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        ns = NotificationService(session)
        await ns.mark_read(notif_id, user_id=user.id)
    return JSONResponse({'ok': True})


@router.post('/read-all')
async def read_all(user=Depends(get_current_user)):
    async with async_session() as session:
        ns = NotificationService(session)
        await ns.mark_all_read(user_id=user.id)
    return JSONResponse({'ok': True})


@router.delete('/delete-all')
async def delete_all(user=Depends(get_current_user)):
    async with async_session() as session:
        ns = NotificationService(session)
        await ns.dismiss_all(user_id=user.id)
    return JSONResponse({'ok': True})


@router.post('/delete-many')
async def delete_many(data: dict, user=Depends(get_current_user)):
    ids = [int(item) for item in (data.get('ids') or []) if item]
    async with async_session() as session:
        ns = NotificationService(session)
        await ns.dismiss_many(ids, user_id=user.id)
    return JSONResponse({'ok': True})


@router.delete('/{notif_id}')
async def delete_notification(notif_id: int, user=Depends(get_current_user)):
    async with async_session() as session:
        ns = NotificationService(session)
        await ns.dismiss(notif_id, user_id=user.id)
    return JSONResponse({'ok': True})


@router.get('/unread-count')
async def unread_count(user=Depends(get_current_user)):
    async with async_session() as session:
        ns = NotificationService(session)
        count = await ns.get_unread_count(user_id=user.id)
    return JSONResponse({'count': count})


@router.put('/users/notification-settings')
async def update_notification_settings(data: dict, user=Depends(get_current_user)):
    async with async_session() as session:
        r = await session.get(UserSettings, 1)
        if not r:
            r = UserSettings(id=1)
            session.add(r)
        if 'calendar_view_mode' in data:
            r.calendar_view_mode = data['calendar_view_mode']
        if 'default_reminder_offset_hours' in data:
            r.default_reminder_offset_hours = data['default_reminder_offset_hours']
        await session.commit()
    return JSONResponse({'ok': True})
