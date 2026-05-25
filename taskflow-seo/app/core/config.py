from pydantic_settings import BaseSettings
from zoneinfo import ZoneInfo
from typing import Optional


class Settings(BaseSettings):
    BOT_TOKEN: str = ''
    DATABASE_URL: str = 'sqlite+aiosqlite:///./data/taskflow.db'
    DEFAULT_TIMEZONE: str = 'Europe/Moscow'
    LOG_LEVEL: str = 'INFO'
    LOG_FILE: str = 'logs/app.log'
    WEB_APP_SECRET: str = ''
    OVERDUE_CHECK_INTERVAL_SECONDS: int = 60
    CONTRACT_REMINDER_DAYS: list[int] = [14, 7, 3, 1]
    DEFAULT_REMINDER_OFFSET_HOURS: int = 1
    RATE_LIMIT_MESSAGES_PER_MINUTE: int = 10

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.DEFAULT_TIMEZONE)


settings = Settings()
