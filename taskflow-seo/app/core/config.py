import os

from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env' if not os.environ.get('TESTING') else None,
        env_file_encoding='utf-8',
    )

    DATABASE_URL: str = 'postgresql+asyncpg://taskflow:taskflow@localhost:5432/taskflow'
    DEFAULT_TIMEZONE: str = 'Europe/Moscow'
    LOG_LEVEL: str = 'INFO'
    LOG_FILE: str = 'logs/app.log'
    WEB_APP_SECRET: str = ''
    OVERDUE_CHECK_INTERVAL_SECONDS: int = 60
    CONTRACT_REMINDER_DAYS: list[int] = [14, 7, 3, 1]
    DEFAULT_REMINDER_OFFSET_HOURS: int = 1
    CRYPTO_SECRET: str = 'taskflow-secret-key-change-in-production'
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.DEFAULT_TIMEZONE)


settings = Settings()