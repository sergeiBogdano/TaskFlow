"""Local server maintenance. No HTTP route exposes these operations."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import hash_password
from app.core.database import async_session, engine
from app.core.models import User


async def rotate_root_password(password: str, session_factory=None) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError('Пароль должен содержать минимум 8 символов')
    factory = session_factory if session_factory is not None else async_session
    async with factory() as session:
        roots = (await session.execute(select(User).where(User.is_root.is_(True)).with_for_update())).scalars().all()
        if len(roots) != 1:
            raise ValueError('В базе должен быть ровно один суперадмин. Проверьте DATABASE_URL и установку приложения.')
        root = roots[0]
        root.password_hash = hash_password(password)
        root.session_version += 1
        root.must_change_password = False
        await session.commit()
        return root.username


def main() -> None:
    parser = argparse.ArgumentParser(description='Обслуживание TaskFlow на сервере')
    parser.add_argument('command', choices=['root-password'])
    parser.parse_args()
    if not sys.stdin.isatty():
        parser.error('Нужен интерактивный терминал. Пароль нельзя передавать аргументом или через pipe.')
    try:
        password = getpass.getpass('Новый пароль суперадмина: ')
        repeated = getpass.getpass('Повторите пароль: ')
        if password != repeated:
            parser.error('Пароли не совпадают')

        async def run():
            try:
                return await rotate_root_password(password)
            finally:
                await engine.dispose()

        username = asyncio.run(run())
    except ValueError as exc:
        parser.error(str(exc))
    except SQLAlchemyError:
        parser.error('Не удалось изменить пароль. Проверьте подключение к базе и применённую схему.')
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, 'Операция отменена.\n')
    else:
        print(f'Пароль суперадмина {username} изменён. Все его прежние сессии отозваны.')


if __name__ == '__main__':
    main()
