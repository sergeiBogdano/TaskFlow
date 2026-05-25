from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.models import Reminder, Task, Client
from app.core.utils.timezone import utc_now, to_user_tz, format_datetime
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class ReminderService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_reminder(
        self,
        trigger_at: datetime,
        message: str,
        reminder_type: str,
        task_id: int | None = None,
        client_id: int | None = None,
    ) -> Reminder:
        if trigger_at.tzinfo is None:
            trigger_at = trigger_at.replace(tzinfo=settings.tz)

        reminder = Reminder(
            task_id=task_id,
            client_id=client_id,
            trigger_at=trigger_at.astimezone(ZoneInfo('UTC')),
            reminder_type=reminder_type,
            message=message,
        )
        self.session.add(reminder)
        await self.session.commit()
        return reminder

    async def get_pending_reminders(self) -> list[Reminder]:
        now = utc_now()
        query = select(Reminder).options(
            selectinload(Reminder.task).selectinload(Task.client),
            selectinload(Reminder.client),
        ).where(
            and_(Reminder.trigger_at <= now, Reminder.sent == False)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_sent(self, reminder_id: int):
        await self.session.execute(
            Reminder.__table__.update().where(Reminder.id == reminder_id).values(sent=True)
        )
        await self.session.commit()

    async def create_contract_reminders(self, client: Client):
        user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
        days = settings.CONTRACT_REMINDER_DAYS

        for days_before in days:
            trigger = client.contract_end - timedelta(days=days_before)
            if trigger > utc_now():
                task_count = len([t for t in client.tasks if t.status in ('todo', 'in_progress', 'overdue')])
                message = (
                    f'📜 Договор с "{client.org_name}" заканчивается через {days_before} дн.\n'
                    f'Активных задач: {task_count}'
                )
                await self.create_reminder(
                    trigger_at=trigger,
                    message=message,
                    reminder_type='contract',
                    client_id=client.id,
                )

    async def create_publish_check_reminder(
        self,
        task: Task,
        check_time: datetime,
    ) -> Reminder:
        client_domain = task.client.domain if task.client else '?'
        message = f'🔔 Проверить публикацию: "{task.title}" на {client_domain}'
        return await self.create_reminder(
            trigger_at=check_time,
            message=message,
            reminder_type='publish_check',
            task_id=task.id,
            client_id=task.client_id,
        )

    async def delete_task_reminders(self, task_id: int):
        from sqlalchemy import delete as sa_delete
        await self.session.execute(
            sa_delete(Reminder).where(and_(Reminder.task_id == task_id, Reminder.sent == False))
        )
        await self.session.commit()

    async def get_unsent_count(self) -> int:
        result = await self.session.execute(
            select(Reminder).where(Reminder.sent == False)
        )
        return len(result.scalars().all())
