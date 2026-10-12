import asyncio

from sqlalchemy import select, update

from app.core.auth import hash_password, verify_password, password_needs_upgrade
from app.core.database import async_session
from app.core.models import User


async def get_user(user_id: int) -> User | None:
    async with async_session() as session:
        return await session.get(User, user_id)


async def get_user_by_username(username: str) -> User | None:
    async with async_session() as session:
        r = await session.execute(select(User).where(User.username == username))
        return r.scalar_one_or_none()


async def create_user(username: str, password: str) -> User:
    async with async_session() as session:
        n = User(username=username, password_hash=hash_password(password))
        session.add(n)
        await session.commit()
        await session.refresh(n)
        return n


_DUMMY_HASH = 'pbkdf2_sha256$600000$' + '0' * 32 + '$' + '0' * 64


async def authenticate(username: str, password: str) -> User | None:
    if not 1 <= len(password) <= 512 or not 2 <= len(username) <= 100:
        return None
    u = await get_user_by_username(username)
    stored = u.password_hash if u and u.is_active else _DUMMY_HASH
    valid = await asyncio.to_thread(verify_password, password, stored)
    if not u or not u.is_active or not valid:
        return None
    if password_needs_upgrade(stored):
        strengthened = await asyncio.to_thread(hash_password, password)
        async with async_session() as session:
            result = await session.execute(update(User).where(User.id == u.id, User.password_hash == stored, User.is_active.is_(True)).values(password_hash=strengthened))
            await session.commit()
            if result.rowcount != 1:
                return None
        u.password_hash = strengthened
    return u
