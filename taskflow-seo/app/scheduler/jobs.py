import logging
import calendar
from datetime import datetime, timedelta
import json

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import Client, FileAttachment, Module, Notification, Task
from app.core.utils.timezone import utc_now
from app.services.client_service import ClientService
from app.services.notification_service import NotificationService
from app.services.reminder_service import ReminderService
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

_last_overdue_notification: dict[int, datetime] = {}
_MAX_NOTIFICATION_CACHE = 1000


def _module_client_ids(module: Module) -> list[int]:
    raw = getattr(module, 'client_ids', None)
    ids: list[int] = []
    if raw:
        try:
            ids = [int(item) for item in json.loads(raw) if item]
        except Exception:
            ids = []
    if not ids and module.client_id:
        ids = [module.client_id]
    return ids


async def check_reminders():
    try:
        async with async_session() as session:
            service = ReminderService(session)
            reminders = await service.get_pending_reminders()

            for reminder in reminders:
                try:
                    await service.mark_sent(reminder.id)
                    logger.info('Напоминание #%d обработано: %s', reminder.id, reminder.message)
                except Exception as e:
                    logger.error('Ошибка обработки напоминания #%d: %s', reminder.id, e)
    except Exception as e:
        logger.error('Ошибка в check_reminders: %s', e)


async def check_overdue_tasks():
    try:
        async with async_session() as session:
            service = TaskService(session)
            overdue_tasks = await service.get_overdue_tasks()
            now = utc_now()

            if len(_last_overdue_notification) > _MAX_NOTIFICATION_CACHE:
                _last_overdue_notification.clear()

            for task in overdue_tasks:
                try:
                    last_notify = _last_overdue_notification.get(task.id)
                    if last_notify and (now - last_notify) < timedelta(hours=24):
                        continue

                    task.status = 'overdue'
                    _last_overdue_notification[task.id] = now

                    logger.info('Задача #%d просрочена', task.id)
                except Exception as e:
                    logger.error('Ошибка обработки просрочки задачи #%d: %s', task.id, e)

            await session.commit()
    except Exception as e:
        logger.error('Ошибка в check_overdue_tasks: %s', e)


async def generate_notifications():
    try:
        async with async_session() as session:
            service = NotificationService(session)
            await service.generate_notifications()
    except Exception as e:
        logger.error('Ошибка в generate_notifications: %s', e)


def _module_due_date(module: Module, today):
    interval = module.recurring_interval or 'monthly'
    day = module.recurring_day
    if interval == 'daily':
        return today
    if interval == 'weekly':
        scheduled_day = day or today.isoweekday()
        return today - timedelta(days=(today.isoweekday() - scheduled_day) % 7)
    if interval == 'monthly':
        scheduled_day = min(day or today.day, calendar.monthrange(today.year, today.month)[1])
        candidate = today.replace(day=scheduled_day)
        if candidate > today:
            return None
        return candidate
    return None


def _module_due_today(module: Module, today) -> bool:
    due_date = _module_due_date(module, today)
    if due_date is None:
        return False
    if not module.last_generated_at:
        return due_date == today
    return module.last_generated_at.date() < due_date


async def generate_module_tasks():
    try:
        async with async_session() as session:
            now = utc_now()
            today = now.date()
            modules = (await session.execute(
                select(Module).where(Module.is_active.is_(True))
            )).scalars().all()

            created_count = 0
            for module in modules:
                if not _module_due_today(module, today):
                    continue

                count = max(1, int(module.recurring_count or 1))
                templates = []
                if getattr(module, 'task_title_templates', None):
                    try:
                        templates = [item for item in json.loads(module.task_title_templates) if item]
                    except Exception:
                        templates = []
                if not templates:
                    templates = [module.task_title_template or module.name]
                for client_id in (_module_client_ids(module) or [None]):
                    for index in range(count):
                        template = templates[index % len(templates)]
                        suffix = f' #{index + 1}' if count > 1 else ''
                        completion_date = now + timedelta(days=int(getattr(module, 'completion_offset_days', 0) or 0))
                        deadline_offset = getattr(module, 'deadline_offset_days', None)
                        generated_task = Task(
                            title=f'{template}{suffix}',
                            client_id=client_id,
                            assignee_id=module.assignee_id,
                            module_id=module.id,
                            task_type=module.task_type or 'custom',
                            priority=getattr(module, 'task_priority', 'medium') or 'medium',
                            notes=getattr(module, 'task_notes_template', None),
                            status='todo',
                            completion_date=completion_date,
                            deadline=(now + timedelta(days=int(deadline_offset))) if deadline_offset is not None else None,
                        )
                        session.add(generated_task)
                        if module.assignee_id:
                            session.add(Notification(
                                task=generated_task,
                                client_id=client_id,
                                user_id=module.assignee_id,
                                notification_type='assigned',
                                title=f'Новая задача по модулю: {generated_task.title}',
                                message='Задача создана автоматически по правилу модуля.',
                                trigger_at=now,
                            ))
                        created_count += 1
                module.last_generated_at = now

            await session.commit()
            if created_count:
                logger.info('Module task generator created %d tasks', created_count)
    except Exception as e:
        logger.error('Error in generate_module_tasks: %s', e)


async def check_contracts_ending():
    try:
        async with async_session() as session:
            service = ClientService(session)
            reminder_service = ReminderService(session)
            clients = await service.get_clients_ending_soon(days=14)

            for client in clients:
                try:
                    await reminder_service.create_contract_reminders(client)
                    logger.info('Напоминания по договору %s созданы', client.org_name)
                except Exception as e:
                    logger.error('Ошибка создания напоминаний для %s: %s', client.org_name, e)
    except Exception as e:
        logger.error('Ошибка в check_contracts_ending: %s', e)


async def autopurge_trash():
    """Удаляет навсегда задачи и клиентов, пробывших в корзине >30 дней."""
    try:
        cutoff = utc_now() - timedelta(days=30)
        async with async_session() as session:
            tasks = (await session.execute(
                select(Task).where(Task.deleted_at.is_not(None), Task.deleted_at < cutoff)
            )).scalars().all()
            for t in tasks:
                await session.execute(sa_delete(FileAttachment).where(FileAttachment.task_id == t.id))
                await session.delete(t)
            clients = (await session.execute(
                select(Client).where(Client.deleted_at.is_not(None), Client.deleted_at < cutoff)
            )).scalars().all()
            for c in clients:
                await session.execute(sa_delete(Task).where(Task.client_id == c.id))
                await session.delete(c)
            await session.commit()
            if tasks or clients:
                logger.info('Автоочистка корзины: удалено %d задач, %d клиентов', len(tasks), len(clients))
    except Exception as e:
        logger.error('Ошибка в autopurge_trash: %s', e)
