from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from app.core.config import settings

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

_user_id: int | None = None


def set_user_id(user_id: int):
    global _user_id
    _user_id = user_id


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
