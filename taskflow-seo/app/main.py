import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from app.core.config import settings

for path in ['data', 'logs']:
    Path(path).mkdir(exist_ok=True)

log_handler = RotatingFileHandler(
    settings.LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8',
)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        log_handler,
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def main():
    logger.info('TaskFlow-SEO запуск (таймзона: %s)', settings.DEFAULT_TIMEZONE)

    config = uvicorn.Config('app.web.app:app', host='0.0.0.0', port=8000, log_level='info')
    server = uvicorn.Server(config)

    try:
        logger.info('Веб-сервер запущен на http://0.0.0.0:8000')
        await server.serve()
    finally:
        logger.info('TaskFlow-SEO завершил работу')


if __name__ == '__main__':
    asyncio.run(main())
