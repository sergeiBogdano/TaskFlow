import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings

logger = logging.getLogger(__name__)

sqlite_url = settings.DATABASE_URL
if sqlite_url.startswith('sqlite+aiosqlite:///'):
    sqlite_url = 'sqlite:///' + sqlite_url[len('sqlite+aiosqlite:///'):]
elif sqlite_url.startswith('postgresql+asyncpg://'):
    sqlite_url = 'postgresql+psycopg://' + sqlite_url[len('postgresql+asyncpg://'):]
jobstores = {
    'default': SQLAlchemyJobStore(url=sqlite_url),
}
scheduler = AsyncIOScheduler(timezone=settings.tz, jobstores=jobstores)


async def start_scheduler():
    from app.scheduler.jobs import check_contracts_ending, check_overdue_tasks, check_reminders, generate_module_tasks, generate_notifications

    interval = settings.OVERDUE_CHECK_INTERVAL_SECONDS

    scheduler.add_job(
        check_reminders,
        IntervalTrigger(seconds=interval),
        id='check_reminders',
        replace_existing=True,
        name='Проверка напоминаний',
    )

    scheduler.add_job(
        check_overdue_tasks,
        IntervalTrigger(seconds=interval),
        id='check_overdue_tasks',
        replace_existing=True,
        name='Проверка просроченных задач',
    )

    scheduler.add_job(
        check_contracts_ending,
        CronTrigger(hour=9, minute=0, timezone=settings.tz),
        id='check_contracts_ending',
        replace_existing=True,
        name='Проверка окончания договоров',
    )

    scheduler.add_job(
        generate_notifications,
        IntervalTrigger(seconds=interval),
        id='generate_notifications',
        replace_existing=True,
        name='Генерация уведомлений',
    )

    scheduler.add_job(
        generate_module_tasks,
        CronTrigger(hour=8, minute=0, timezone=settings.tz),
        id='generate_module_tasks',
        replace_existing=True,
        name='Auto module task generation',
    )

    from app.scheduler.jobs import autopurge_trash
    scheduler.add_job(
        autopurge_trash,
        CronTrigger(hour=3, minute=0, timezone=settings.tz),
        id='autopurge_trash',
        replace_existing=True,
        name='Очистка корзины',
    )

    # Catch up rules that were due while the application was stopped.
    await generate_module_tasks()
    scheduler.start()
    logger.info('Планировщик запущен')


async def stop_scheduler():
    scheduler.shutdown(wait=False)
    logger.info('Планировщик остановлен')
