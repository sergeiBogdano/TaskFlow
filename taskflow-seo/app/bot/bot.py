from __future__ import annotations
from typing import Any, Awaitable, Callable
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from app.core.config import settings
from typing import Optional

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

_user_id: Optional[int] = None


def set_user_id(user_id: int):
    global _user_id
    _user_id = user_id


class UserIdMiddleware:
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, types.Message):
            user = event.from_user
        elif isinstance(event, types.CallbackQuery):
            user = event.from_user
        if user:
            set_user_id(user.id)
        return await handler(event, data)


async def notify_user(reminder):
    if _user_id:
        from app.bot.keyboards import get_reminder_keyboard
        kb = get_reminder_keyboard(reminder)
        await bot.send_message(_user_id, reminder.message, reply_markup=kb)


async def notify_overdue(task):
    if _user_id:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.core.utils.timezone import format_datetime
        tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
        deadline_str = format_datetime(task.deadline, tz) if task.deadline else 'не указан'
        from app.bot.keyboards import get_overdue_keyboard
        kb = get_overdue_keyboard(task.id)
        client_info = f' ({task.client.org_name})' if task.client else ''
        await bot.send_message(
            _user_id,
            f'⚠️ Задача просрочена!\n#{task.id} {task.title}{client_info}\n'
            f'Дедлайн был: {deadline_str}',
            reply_markup=kb,
        )
