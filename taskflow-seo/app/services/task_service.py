from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.models import Task, Reminder, Client
from app.core.utils.timezone import utc_now, to_utc
from app.core.config import settings


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
        priority: str = 'medium',
        checklist: list | None = None,
    ) -> Task:
        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=settings.tz)
        if deadline:
            deadline = to_utc(deadline)

        task = Task(
            client_id=client_id,
            title=title,
            task_type=task_type,
            notes=notes,
            comment=comment,
            deadline=deadline,
            priority=priority,
            status='todo',
            checklist=checklist or [],
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
            select(Task).options(selectinload(Task.client)).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        status: str | None = None,
        client_id: int | None = None,
        tag: str | None = None,
        task_type: str | None = None,
    ) -> list[Task]:
        query = select(Task).options(selectinload(Task.client))

        conditions = []
        if status:
            conditions.append(Task.status == status)
        if client_id is not None:
            conditions.append(Task.client_id == client_id)
        if task_type:
            conditions.append(Task.task_type == task_type)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Task.deadline.asc().nullslast())
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
                and_(Reminder.task_id == task_id, Reminder.sent == False)
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

    async def add_note(self, task_id: int, note_text: str) -> Task | None:
        task = await self.get_task(task_id)
        if not task:
            return None
        if task.notes:
            task.notes += f'\n{note_text}'
        else:
            task.notes = note_text
        await self.session.commit()
        return task

    async def mark_done(self, task_id: int) -> Task | None:
        task = await self.get_task(task_id)
        if not task:
            return None
        task.status = 'done'
        await self.session.execute(
            delete(Reminder).where(
                and_(Reminder.task_id == task_id, Reminder.sent == False)
            )
        )
        await self.session.commit()
        return task

    async def get_client_tasks(self, client_id: int) -> list[Task]:
        return await self.list_tasks(client_id=client_id)

    async def get_active_client_tasks(self, client_id: int) -> list[Task]:
        query = select(Task).where(
            and_(Task.client_id == client_id, Task.status.in_(['todo', 'in_progress', 'overdue']))
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_tasks_by_domain(self, domain: str) -> list[Task]:
        query = select(Task).options(selectinload(Task.client)).join(Client).where(Client.domain == domain)
        result = await self.session.execute(query)
        return list(result.scalars().all())

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

    async def get_tasks_due_today(self, user_tz: ZoneInfo) -> list[Task]:
        now = datetime.now(user_tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        start_utc = to_utc(start)
        end_utc = to_utc(end)
        query = select(Task).options(selectinload(Task.client)).where(
            and_(Task.deadline >= start_utc, Task.deadline < end_utc, Task.status != 'done')
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_tasks_due_tomorrow(self, user_tz: ZoneInfo) -> list[Task]:
        now = datetime.now(user_tz)
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        start_utc = to_utc(start)
        end_utc = to_utc(end)
        query = select(Task).options(selectinload(Task.client)).where(
            and_(Task.deadline >= start_utc, Task.deadline < end_utc, Task.status != 'done')
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
