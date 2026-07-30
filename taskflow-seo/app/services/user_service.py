
from sqlalchemy import select

from app.core.auth import hash_password, verify_password
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


async def authenticate(username: str, password: str) -> User | None:
    u = await get_user_by_username(username)
    if u and verify_password(password, u.password_hash):
        return u
    return None
