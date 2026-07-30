from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.models import ClientResponsible, Notification, Task
from app.core.utils.timezone import utc_now

logger = logging.getLogger(__name__)


NOTIFICATION_TYPES = {
    'overdue': 'Просрочено',
    'deadline': 'Дедлайн',
    'checklist': 'Чек-лист',
    'publish': 'Публикация',
    'contract': 'Договор',
    'stale': 'Зависшая задача',
}


class NotificationService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_notifications(self):
        now = utc_now()
        count = 0

        responsible_result = await self.session.execute(select(ClientResponsible))
        responsible_by_client: dict[int, set[int]] = {}
        for row in responsible_result.scalars().all():
            responsible_by_client.setdefault(row.client_id, set()).add(row.user_id)

        def recipients(task: Task) -> set[int]:
            ids = {task.creator_id, task.assignee_id}
            ids.update(link.user_id for link in (task.co_executor_links or []))
            ids.update(responsible_by_client.get(task.client_id, set()))
            return {item for item in ids if item}

        existing = await self.session.execute(
            select(Notification.task_id, Notification.user_id).where(
                Notification.notification_type == 'overdue',
            )
        )
        existing_overdue = {(r[0], r[1]) for r in existing if r[0]}

        tasks = await self.session.execute(
            select(Task).options(selectinload(Task.client), selectinload(Task.co_executor_links)).where(
                and_(
                    Task.deadline < now,
                    Task.status != 'done',
                    Task.deleted_at.is_(None),
                )
            )
        )
        for task in tasks.scalars().all():
            client_name = task.client.org_name if task.client else ''
            for target_user_id in recipients(task):
                if (task.id, target_user_id) in existing_overdue:
                    continue
                self.session.add(Notification(
                    task_id=task.id,
                    client_id=task.client_id,
                    user_id=target_user_id,
                    notification_type='overdue',
                    title=f'Просрочена задача #{task.id}',
                    message=f'{task.title}' + (f' ({client_name})' if client_name else ''),
                    trigger_at=now,
                ))
                count += 1

        existing_checklist = await self.session.execute(
            select(Notification.task_id, Notification.checklist_idx, Notification.user_id).where(
                Notification.notification_type == 'checklist',
            )
        )
        existing_cl_set = {(r[0], r[1], r[2]) for r in existing_checklist if r[0]}

        tasks_with_checklist = await self.session.execute(
            select(Task).options(selectinload(Task.client), selectinload(Task.co_executor_links)).where(
                Task.checklist.isnot(None),
                Task.deleted_at.is_(None),
            )
        )
        for task in tasks_with_checklist.scalars().all():
            if not task.checklist:
                continue
            for idx, ci in enumerate(task.checklist):
                if ci.get('done'):
                    continue
                reminder_raw = ci.get('reminder')
                if not reminder_raw:
                    continue
                try:
                    reminder_dt = datetime.fromisoformat(reminder_raw)
                    if reminder_dt.tzinfo is None:
                        reminder_dt = reminder_dt.replace(tzinfo=ZoneInfo('UTC'))
                except (ValueError, TypeError):
                    continue
                if reminder_dt > now:
                    continue
                for target_user_id in recipients(task):
                    if (task.id, idx, target_user_id) in existing_cl_set:
                        continue
                    self.session.add(Notification(
                        task_id=task.id,
                        client_id=task.client_id,
                        user_id=target_user_id,
                        notification_type='checklist',
                        checklist_idx=idx,
                        title=f'Напоминание: {ci.get("text", "?")}',
                        message=f'Чек-лист задачи #{task.id}: {task.title}',
                        trigger_at=now,
                    ))
                    count += 1

        stale_cutoff = now - timedelta(days=7)
        stale_tasks_result = await self.session.execute(
            select(Task).options(selectinload(Task.client), selectinload(Task.co_executor_links)).where(
                Task.status != 'done',
                Task.deleted_at.is_(None),
                or_(
                    Task.updated_at < stale_cutoff,
                    and_(Task.updated_at.is_(None), Task.created_at < stale_cutoff),
                ),
            )
        )
        stale_tasks = stale_tasks_result.scalars().all()
        client_ids = {task.client_id for task in stale_tasks if task.client_id}
        existing_stale = await self.session.execute(
            select(Notification.task_id, Notification.user_id).where(
                Notification.notification_type == 'stale',
            )
        )
        existing_stale_pairs = {(row[0], row[1]) for row in existing_stale}
        for task in stale_tasks:
            targets = {task.assignee_id, *(link.user_id for link in (task.co_executor_links or []))}
            targets.update(responsible_by_client.get(task.client_id, set()))
            targets = {target for target in targets if target}
            for target in targets:
                if (task.id, target) in existing_stale_pairs:
                    continue
                client_name = task.client.org_name if task.client else ''
                self.session.add(Notification(
                    task_id=task.id,
                    client_id=task.client_id,
                    user_id=target,
                    notification_type='stale',
                    title=f'Задача без изменений 7 дней: #{task.id}',
                    message=f'{task.title}' + (f' ({client_name})' if client_name else ''),
                    trigger_at=now,
                ))
                count += 1

        if count:
            await self.session.commit()
            logger.info('Создано %d уведомлений', count)
        return count

    async def list_notifications(
        self,
        unread_only: bool = False,
        limit: int = 100,
        offset: int = 0,
        user_id: int | None = None,
    ) -> list[Notification]:
        query = select(Notification).options(
            selectinload(Notification.task).selectinload(Task.client),
        ).order_by(Notification.created_at.desc())
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.read.is_(False))
        query = query.offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_unread_count(self, user_id: int | None = None) -> int:
        query = select(func.count()).select_from(Notification).where(Notification.read.is_(False))
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def mark_read(self, notification_id: int, user_id: int | None = None):
        query = select(Notification).where(Notification.id == notification_id)
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        notif = (await self.session.execute(query)).scalar_one_or_none()
        if notif:
            notif.read = True
            await self.session.commit()

    async def mark_all_read(self, user_id: int | None = None):
        query = update(Notification).where(Notification.read.is_(False))
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        await self.session.execute(query.values(read=True))
        await self.session.commit()

    async def dismiss(self, notification_id: int, user_id: int | None = None):
        query = select(Notification).where(Notification.id == notification_id)
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        notif = (await self.session.execute(query)).scalar_one_or_none()
        if notif:
            await self.session.delete(notif)
            await self.session.commit()

    async def dismiss_many(self, notification_ids: list[int], user_id: int | None = None):
        if not notification_ids:
            return
        query = sa_delete(Notification).where(Notification.id.in_(notification_ids))
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        await self.session.execute(query)
        await self.session.commit()

    async def dismiss_all(self, user_id: int | None = None):
        query = sa_delete(Notification)
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        await self.session.execute(query)
        await self.session.commit()

    async def dismiss_all_read(self, user_id: int | None = None):
        query = sa_delete(Notification).where(Notification.read.is_(True))
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        await self.session.execute(
            query
        )
        await self.session.commit()
