from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.models import Client, Reminder, Task
from app.core.utils.timezone import to_utc, utc_now


class TaskService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_task(
        self,
        title: str,
        client_id: int | None = None,
        task_type: str = 'custom',
        notes: str | None = None,
        comment: str | None = None,
        deadline: datetime | None = None,
        completion_date: datetime | None = None,
        priority: str = 'medium',
        checklist: list | None = None,
    ) -> Task:
        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=settings.tz)
        if deadline:
            deadline = to_utc(deadline)
        if completion_date and completion_date.tzinfo is None:
            completion_date = completion_date.replace(tzinfo=settings.tz)
        if completion_date:
            completion_date = to_utc(completion_date)

        task = Task(
            client_id=client_id,
            title=title,
            task_type=task_type,
            notes=notes,
            comment=comment,
            deadline=deadline,
            completion_date=completion_date,
            priority=priority,
            status='todo',
            checklist=checklist,
        )
        self.session.add(task)
        await self.session.flush()

        if deadline:
            offset = timedelta(hours=settings.DEFAULT_REMINDER_OFFSET_HOURS)
            reminder_time = deadline - offset
            if reminder_time > utc_now():
                reminder = Reminder(
                    task_id=task.id,
                    client_id=client_id,
                    trigger_at=reminder_time,
                    reminder_type='deadline',
                    message=f'🔔 Напоминание: "{title}" — дедлайн через {settings.DEFAULT_REMINDER_OFFSET_HOURS} ч.',
                )
                self.session.add(reminder)

        await self.session.commit()
        return task

    async def get_task(self, task_id: int) -> Task | None:
        result = await self.session.execute(
            select(Task).options(
                selectinload(Task.client),
                selectinload(Task.co_executor_links),
            ).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        status: str | None = None,
        client_id: int | None = None,
        tag: str | None = None,
        task_type: str | None = None,
        priority: str | None = None,
    ) -> list[Task]:
        query = select(Task).options(
            selectinload(Task.client),
            selectinload(Task.co_executor_links),
        ).where(Task.deleted_at.is_(None))

        conditions = []
        if status:
            statuses = [item.strip() for item in status.split(',') if item.strip()]
            if statuses:
                conditions.append(Task.status.in_(statuses))
        if client_id is not None:
            conditions.append(Task.client_id == client_id)
        if task_type:
            conditions.append(Task.task_type == task_type)
        if priority:
            conditions.append(Task.priority == priority)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Task.id.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(self, task_id: int, new_status: str) -> Task | None:
        task = await self.get_task(task_id)
        if not task:
            return None
        task.status = new_status
        await self.session.commit()
        return task

    async def snooze(self, task_id: int, new_deadline: datetime) -> Task | None:
        task = await self.get_task(task_id)
        if not task:
            return None

        if new_deadline.tzinfo is None:
            new_deadline = new_deadline.replace(tzinfo=settings.tz)
        task.deadline = to_utc(new_deadline)

        if task.status == 'todo':
            task.status = 'in_progress'

        await self.session.execute(
            delete(Reminder).where(
                and_(Reminder.task_id == task_id, Reminder.sent.is_(False))
            )
        )

        offset = timedelta(hours=settings.DEFAULT_REMINDER_OFFSET_HOURS)
        reminder_time = task.deadline - offset
        if reminder_time > utc_now():
            reminder = Reminder(
                task_id=task_id,
                client_id=task.client_id,
                trigger_at=reminder_time,
                reminder_type='deadline',
                message=f'🔔 Напоминание: "{task.title}" — новый дедлайн через {settings.DEFAULT_REMINDER_OFFSET_HOURS} ч.',
            )
            self.session.add(reminder)

        await self.session.commit()
        return task

    async def get_overdue_tasks(self) -> list[Task]:
        now = utc_now()
        query = select(Task).options(selectinload(Task.client)).where(
            and_(
                Task.deadline < now,
                Task.status != 'done',
                Task.status != 'overdue',
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
