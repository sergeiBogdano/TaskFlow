from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.core.models import Reminder


def get_main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text='📋 Мои задачи', callback_data='list_all')
    kb.button(text='➕ Новая задача', callback_data='add_task')
    kb.button(text='📦 Новый клиент', callback_data='new_client')
    kb.button(text='📝 Статьи', callback_data='articles')
    kb.button(text='⚙️ Настройки', callback_data='settings')
    kb.adjust(2)
    return kb.as_markup()


def get_template_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text='🌐 Создание сайта', callback_data='template_site_creation')
    kb.button(text='📝 Контент/Статьи', callback_data='template_content_articles')
    kb.button(text='🔍 Тех. аудит', callback_data='template_tech_audit')
    kb.button(text='📦 Пустой', callback_data='template_empty')
    kb.adjust(1)
    return kb.as_markup()


def get_task_actions_keyboard(task_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text='✅ Выполнено', callback_data=f'done_{task_id}')
    kb.button(text='⏰ Отложить', callback_data=f'snooze_{task_id}')
    kb.button(text='📝 Заметка', callback_data=f'note_{task_id}')
    kb.adjust(3)
    return kb.as_markup()


def get_overdue_keyboard(task_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text='✅ Выполнено', callback_data=f'done_{task_id}')
    kb.button(text='⏰ +1ч', callback_data=f'snooze_{task_id}_1h')
    kb.button(text='⏰ +1д', callback_data=f'snooze_{task_id}_1d')
    kb.button(text='📝 Заметка', callback_data=f'note_{task_id}')
    kb.adjust(2)
    return kb.as_markup()


def get_reminder_keyboard(reminder: Reminder):
    kb = InlineKeyboardBuilder()
    if reminder.task_id:
        kb.button(text='✅ Выполнено', callback_data=f'done_{reminder.task_id}')
        kb.button(text='⏰ Отложить', callback_data=f'snooze_{reminder.task_id}')
    if reminder.client_id and reminder.reminder_type == 'contract':
        kb.button(text='📅 Продлить', callback_data=f'extend_{reminder.client_id}')
        kb.button(text='📋 Задачи', callback_data=f'client_tasks_{reminder.client_id}')
    kb.button(text='📝 Заметка', callback_data=f'note_{reminder.task_id}' if reminder.task_id else 'ignore')
    kb.adjust(2)
    return kb.as_markup()


def get_confirm_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text='✅ Да', callback_data='confirm_yes')
    kb.button(text='❌ Нет', callback_data='confirm_no')
    return kb.as_markup()


def get_settings_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text='🌍 Часовой пояс', callback_data='settings_timezone')
    kb.button(text='⏰ Напоминания', callback_data='settings_reminder_offset')
    kb.button(text='📋 Текущие настройки', callback_data='settings_show')
    kb.adjust(1)
    return kb.as_markup()


def get_timezone_keyboard():
    tzs = ['Europe/Moscow', 'Europe/Samara', 'Europe/Kaliningrad', 'Asia/Yekaterinburg',
           'Asia/Novosibirsk', 'Asia/Vladivostok', 'Asia/Kamchatka']
    kb = InlineKeyboardBuilder()
    for tz in tzs:
        label = tz.split('/')[-1].replace('_', ' ')
        kb.button(text=f'{label} (UTC)', callback_data=f'tz_{tz}')
    kb.adjust(1)
    return kb.as_markup()


def get_reminder_offset_keyboard():
    kb = InlineKeyboardBuilder()
    for h in [1, 2, 3, 6, 12, 24]:
        kb.button(text=f'За {h} ч.', callback_data=f'roff_{h}')
    kb.adjust(3)
    return kb.as_markup()


def get_pagination_keyboard(page: int, total_pages: int, prefix: str = 'list'):
    kb = InlineKeyboardBuilder()
    if page > 0:
        kb.button(text='◀️ Назад', callback_data=f'{prefix}_page_{page - 1}')
    if page < total_pages - 1:
        kb.button(text='▶️ Вперёд', callback_data=f'{prefix}_page_{page + 1}')
    kb.adjust(2)
    return kb.as_markup()
