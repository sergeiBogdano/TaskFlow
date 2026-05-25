from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=settings.tz)


async def start_scheduler():
    from app.scheduler.jobs import check_reminders, check_overdue_tasks, check_contracts_ending

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

    scheduler.start()
    logger.info('Планировщик запущен')


async def stop_scheduler():
    scheduler.shutdown(wait=False)
    logger.info('Планировщик остановлен')
