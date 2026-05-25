from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.core.database import async_session
from app.core.utils.timezone import utc_now, to_user_tz, to_utc, format_datetime, parse_deadline
from app.core.config import settings
from app.services.task_service import TaskService
from app.services.client_service import ClientService
from app.services.reminder_service import ReminderService
from app.bot.keyboards import get_task_actions_keyboard

router = Router()


class ArticleStates(StatesGroup):
    waiting_domain = State()
    waiting_topics = State()
    waiting_deadline = State()


article_data: dict = {}


@router.callback_query(F.data == 'articles')
async def cb_articles(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.set_state(ArticleStates.waiting_domain)
    await callback.message.answer('🌐 Введите домен клиента. Например: <code>spbpack.net</code>', parse_mode='HTML')
    await callback.answer()


@router.message(ArticleStates.waiting_domain)
async def process_domain_input(message: types.Message, state: FSMContext):
    domain = message.text.strip()
    async with async_session() as session:
        client_service = ClientService(session)
        client = await client_service.get_client_by_domain(domain)
        if not client:
            await message.answer(f'❌ Клиент с доменом {domain} не найден. Проверьте написание.')
            return

    await state.update_data(domain=domain, client_id=client.id, client_org=client.org_name)
    await state.set_state(ArticleStates.waiting_topics)
    await message.answer(
        f'📝 Введите темы статей (каждая с новой строки):\n'
        f'<i>Клиент: {client.org_name} ({domain})</i>',
        parse_mode='HTML',
    )


@router.message(Command('articles'))
async def cmd_articles(message: types.Message, state: FSMContext):
    text = message.text.removeprefix('/articles').strip()
    if not text:
        await message.answer('❌ Укажите домен. Пример: /articles spbpack.net')
        return

    domain = text.split()[0]
    async with async_session() as session:
        client_service = ClientService(session)
        client = await client_service.get_client_by_domain(domain)
        if not client:
            await message.answer(f'❌ Клиент с доменом {domain} не найден.')
            return

    await state.set_state(ArticleStates.waiting_topics)
    await state.update_data(domain=domain, client_id=client.id, client_org=client.org_name)
    await message.answer(
        f'📝 Введите темы статей (каждая с новой строки):\n'
        f'<i>Клиент: {client.org_name} ({domain})</i>',
        parse_mode='HTML',
    )


@router.message(ArticleStates.waiting_topics)
async def process_topics(message: types.Message, state: FSMContext):
    topics = [t.strip() for t in message.text.strip().split('\n') if t.strip()]
    if not topics:
        await message.answer('❌ Введите хотя бы одну тему.')
        return

    data = await state.get_data()
    data['topics'] = topics
    data['current_topic_idx'] = 0

    await state.update_data(data)
    await state.set_state(ArticleStates.waiting_deadline)

    await message.answer(
        f'📅 Укажите дату проверки публикации для:\n'
        f'<b>"{topics[0]}"</b>\n'
        f'Пример: завтра 18:00, 28.06 14:00, +3д',
        parse_mode='HTML',
    )


@router.message(ArticleStates.waiting_deadline)
async def process_article_deadline(message: types.Message, state: FSMContext):
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    data = await state.get_data()
    idx = data['current_topic_idx']
    topics = data['topics']

    deadline = parse_deadline(message.text.strip(), user_tz)
    if not deadline:
        await message.answer('❌ Не удалось распознать дату. Пример: завтра 18:00, 28.06 14:00')
        return

    if 'deadlines' not in data:
        data['deadlines'] = {}
    data['deadlines'][idx] = deadline
    await state.update_data(data)

    idx += 1
    if idx < len(topics):
        await state.update_data(current_topic_idx=idx)
        await message.answer(
            f'📅 Укажите дату проверки публикации для:\n'
            f'<b>"{topics[idx]}"</b>',
            parse_mode='HTML',
        )
    else:
        await create_articles(message, state)
        await state.clear()


async def create_articles(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)

    async with async_session() as session:
        task_service = TaskService(session)
        reminder_service = ReminderService(session)

        checklist = [
            {'text': 'Черновик', 'done': False},
            {'text': 'Правки', 'done': False},
            {'text': 'Публикация', 'done': False},
            {'text': 'Проверка', 'done': False},
        ]

        created = []
        for idx, topic in enumerate(data['topics']):
            deadline = data['deadlines'].get(idx)
            task = await task_service.create_task(
                title=topic,
                client_id=data['client_id'],
                task_type='article',
                deadline=deadline,
                checklist=checklist,
            )

            if deadline:
                await reminder_service.create_publish_check_reminder(task, deadline)

            created.append(task)

        lines = [f'✅ Создано {len(created)} статей для {data.get("client_org", "?")}:']
        for t in created:
            dl = format_datetime(t.deadline, user_tz) if t.deadline else '?'
            lines.append(f'  #{t.id} {t.title} — проверка {dl}')

        await message.answer('\n'.join(lines))
