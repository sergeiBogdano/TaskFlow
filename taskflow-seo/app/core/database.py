from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def _migrate():
    """Add missing columns for schema upgrades."""
    async with engine.begin() as conn:
        for col in [
            'ALTER TABLE tasks ADD COLUMN comment TEXT',
            'ALTER TABLE clients ADD COLUMN org_data TEXT',
        ]:
            try:
                await conn.execute(text(col))
            except Exception:
                pass


async def init_db():
    from app.core.models import Client, Task, Reminder, UserSettings
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate()


async def close_db():
    await engine.dispose()
