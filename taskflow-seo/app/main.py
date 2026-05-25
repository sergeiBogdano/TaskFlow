import asyncio
import logging
from pathlib import Path

from app.core.config import settings
from app.core.database import init_db, close_db
from app.scheduler.scheduler import start_scheduler, stop_scheduler
from app.bot.bot import UserIdMiddleware

for path in ['data', 'logs', 'templates', 'backups']:
    Path(path).mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(settings.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def main():
    logger.info(f'🚀 TaskFlow-SEO запуск (таймзона: {settings.DEFAULT_TIMEZONE})')

    await init_db()
    logger.info('✅ База данных инициализирована')

    from app.bot.bot import bot, dp
    from app.bot.handlers.start import router as start_router
    from app.bot.handlers.tasks import router as tasks_router
    from app.bot.handlers.clients import router as clients_router
    from app.bot.handlers.articles import router as articles_router
    from app.bot.handlers.settings import router as settings_router

    dp.include_router(start_router)
    dp.include_router(tasks_router)
    dp.include_router(clients_router)
    dp.include_router(articles_router)
    dp.include_router(settings_router)

    dp.message.middleware(UserIdMiddleware())
    dp.callback_query.middleware(UserIdMiddleware())

    await start_scheduler()

    try:
        logger.info('🤖 Бот запущен')
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await stop_scheduler()
        await close_db()
        logger.info('👋 TaskFlow-SEO завершил работу')


if __name__ == '__main__':
    asyncio.run(main())
