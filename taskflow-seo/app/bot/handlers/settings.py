from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import UserSettings
from app.core.config import settings as app_settings
from app.bot.keyboards import get_settings_keyboard, get_timezone_keyboard, get_reminder_offset_keyboard

router = Router()


class SettingsStates(StatesGroup):
    waiting_timezone = State()
    waiting_reminder_offset = State()


async def get_user_settings() -> UserSettings:
    async with async_session() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.id == 1))
        us = result.scalar_one_or_none()
        if not us:
            us = UserSettings(
                id=1,
                timezone=app_settings.DEFAULT_TIMEZONE,
                default_reminder_offset_hours=app_settings.DEFAULT_REMINDER_OFFSET_HOURS,
            )
            session.add(us)
            await session.commit()
        return us


async def update_user_settings(**kwargs):
    async with async_session() as session:
        result = await session.execute(select(UserSettings).where(UserSettings.id == 1))
        us = result.scalar_one_or_none()
        if not us:
            us = UserSettings(id=1)
            session.add(us)
        for k, v in kwargs.items():
            setattr(us, k, v)
        await session.commit()


@router.message(Command('settings'))
async def cmd_settings(message: types.Message):
    await message.answer('⚙️ <b>Настройки</b>', parse_mode='HTML', reply_markup=get_settings_keyboard())


@router.callback_query(F.data == 'settings_show')
async def cb_settings_show(callback: types.CallbackQuery):
    us = await get_user_settings()
    await callback.message.edit_text(
        f'⚙️ <b>Текущие настройки</b>\n\n'
        f'🌍 Часовой пояс: <code>{us.timezone}</code>\n'
        f'⏰ Напоминание за: {us.default_reminder_offset_hours} ч.\n'
        f'📅 Последняя синхр.: {us.last_sync or "—"}',
        parse_mode='HTML',
        reply_markup=get_settings_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == 'settings_timezone')
async def cb_settings_timezone(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_timezone)
    await callback.message.edit_text(
        '🌍 Выберите часовой пояс:',
        reply_markup=get_timezone_keyboard(),
    )
    await callback.answer()


@router.callback_query(SettingsStates.waiting_timezone, F.data.startswith('tz_'))
async def cb_tz_selected(callback: types.CallbackQuery, state: FSMContext):
    tz = callback.data.replace('tz_', '')
    await update_user_settings(timezone=tz)
    app_settings.DEFAULT_TIMEZONE = tz
    await state.clear()
    await callback.message.edit_text(f'✅ Часовой пояс изменён на <code>{tz}</code>', parse_mode='HTML')
    await callback.answer()


@router.callback_query(F.data == 'settings_reminder_offset')
async def cb_settings_offset(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_reminder_offset)
    await callback.message.edit_text(
        '⏰ За сколько часов напоминать до дедлайна?',
        reply_markup=get_reminder_offset_keyboard(),
    )
    await callback.answer()


@router.callback_query(SettingsStates.waiting_reminder_offset, F.data.startswith('roff_'))
async def cb_offset_selected(callback: types.CallbackQuery, state: FSMContext):
    hours = int(callback.data.replace('roff_', ''))
    await update_user_settings(default_reminder_offset_hours=hours)
    app_settings.DEFAULT_REMINDER_OFFSET_HOURS = hours
    await state.clear()
    await callback.message.edit_text(f'✅ Напоминание установлено за {hours} ч. до дедлайна.')
    await callback.answer()
