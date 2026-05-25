from aiogram import Router, types
from aiogram.filters import Command
from app.bot.bot import set_user_id
from app.bot.keyboards import get_main_keyboard

router = Router()


@router.message(Command('start'))
async def cmd_start(message: types.Message):
    set_user_id(message.from_user.id)
    await message.answer(
        '🚀 <b>TaskFlow-SEO</b> — твой личный таск-менеджер для веб/SEO\n\n'
        'Что умею:\n'
        '• 📋 Ставить задачи через /add\n'
        '• 📦 Создавать проекты с шаблонами через /new_client\n'
        '• 📝 Пакетное создание статей через /articles\n'
        '• 🔔 Напоминать о дедлайнах и договорах\n'
        '• ⚙️ Настраивать часовой пояс через /settings\n\n'
        'Отправь /help для списка команд',
        reply_markup=get_main_keyboard(),
        parse_mode='HTML',
    )


@router.message(Command('help'))
async def cmd_help(message: types.Message):
    set_user_id(message.from_user.id)
    help_text = (
        '📚 <b>Справка TaskFlow-SEO</b>\n\n'
        'Команды:\n'
        '• /start — приветствие\n'
        '• /help — эта справка\n'
        '• /add [текст] [#теги] [~дедлайн] — быстрая задача\n'
        '• /list [фильтр] — просмотр задач\n'
        '• /done [id] — отметить выполненной\n'
        '• /snooze [id] [время] — отложить\n'
        '• /note [id] [текст] — добавить заметку\n'
        '• /new_client — новый проект/клиент\n'
        '• /articles [домен] — пакет статей\n'
        '• /settings — настройки\n\n'
        'Примеры:\n'
        '<code>/add Написать статью #spbpack ~завтра 18:00</code>\n'
        '<code>/add Проверить индексацию #seo ~+3д</code>\n'
        '<code>/list #статья</code>\n'
        '<code>/list spbpack status:todo</code>'
    )
    await message.answer(help_text, parse_mode='HTML')
