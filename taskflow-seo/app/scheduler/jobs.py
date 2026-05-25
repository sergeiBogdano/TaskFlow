import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session
from app.core.utils.timezone import utc_now, to_user_tz
from app.services.reminder_service import ReminderService
from app.services.task_service import TaskService
from app.services.client_service import ClientService
from app.core.config import settings

logger = logging.getLogger(__name__)

_last_overdue_notification: dict[int, datetime] = {}


async def check_reminders():
    try:
        async with async_session() as session:
            service = ReminderService(session)
            reminders = await service.get_pending_reminders()

            for reminder in reminders:
                try:
                    from app.bot.bot import notify_user
                    await notify_user(reminder)
                    await service.mark_sent(reminder.id)
                    logger.info(f'Напоминание #{reminder.id} отправлено')
                except Exception as e:
                    logger.error(f'Ошибка отправки напоминания #{reminder.id}: {e}')
    except Exception as e:
        logger.error(f'Ошибка в check_reminders: {e}')


async def check_overdue_tasks():
    try:
        async with async_session() as session:
            service = TaskService(session)
            overdue_tasks = await service.get_overdue_tasks()
            now = utc_now()

            for task in overdue_tasks:
                try:
                    last_notify = _last_overdue_notification.get(task.id)
                    if last_notify and (now - last_notify) < timedelta(hours=24):
                        continue

                    task.status = 'overdue'
                    _last_overdue_notification[task.id] = now

                    from app.bot.bot import notify_overdue
                    await notify_overdue(task)

                    logger.info(f'Задача #{task.id} просрочена, уведомление отправлено')
                except Exception as e:
                    logger.error(f'Ошибка обработки просрочки задачи #{task.id}: {e}')

            await session.commit()
    except Exception as e:
        logger.error(f'Ошибка в check_overdue_tasks: {e}')


async def check_contracts_ending():
    try:
        async with async_session() as session:
            service = ClientService(session)
            reminder_service = ReminderService(session)
            clients = await service.get_clients_ending_soon(days=14)

            for client in clients:
                try:
                    await reminder_service.create_contract_reminders(client)
                    logger.info(f'Напоминания по договору {client.org_name} созданы')
                except Exception as e:
                    logger.error(f'Ошибка создания напоминаний для {client.org_name}: {e}')
    except Exception as e:
        logger.error(f'Ошибка в check_contracts_ending: {e}')
