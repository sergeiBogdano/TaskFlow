import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.utils.timezone import utc_now, to_user_tz, to_utc, format_datetime, parse_deadline
from app.core.utils.validators import parse_add_command
from app.core.config import settings
from app.services.task_service import TaskService
from app.services.client_service import ClientService
from app.bot.keyboards import get_task_actions_keyboard, get_pagination_keyboard

router = Router()

PAGE_SIZE = 10


class TaskStates(StatesGroup):
    waiting_snooze_time = State()
    waiting_note_text = State()


@router.message(Command('add'))
async def cmd_add(message: types.Message):
    text = message.text.removeprefix('/add').strip()
    if not text:
        await message.answer('❌ Укажите текст задачи. Пример:\n<code>/add Написать статью #spbpack ~завтра 18:00</code>', parse_mode='HTML')
        return

    parsed = parse_add_command(text)
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)

    deadline = None
    if parsed.deadline_raw:
        deadline = parse_deadline(parsed.deadline_raw, user_tz)
        if not deadline:
            await message.answer(f'❌ Не удалось распознать время: {parsed.deadline_raw}')

    async with async_session() as session:
        service = TaskService(session)
        client_service = ClientService(session)

        client_id = None
        client_info = ''
        if parsed.client_domain:
            client = await client_service.get_client_by_domain(parsed.client_domain)
            if client:
                client_id = client.id
                client_info = f' ({client.org_name})'

        task = await service.create_task(
            title=parsed.title,
            client_id=client_id,
            deadline=deadline,
        )

        deadline_str = format_datetime(task.deadline, user_tz) if task.deadline else 'не указан'
        tags_str = ' '.join(f'#{t}' for t in parsed.tags) if parsed.tags else ''

        await message.answer(
            f'✅ Задача #{task.id} создана{client_info}\n'
            f'📌 {task.title}\n'
            f'{tags_str}\n'
            f'📅 Дедлайн: {deadline_str}\n'
            f'🔔 Напомню за {settings.DEFAULT_REMINDER_OFFSET_HOURS} ч.',
            reply_markup=get_task_actions_keyboard(task.id),
        )


@router.message(Command('list'))
async def cmd_list(message: types.Message):
    text = message.text.removeprefix('/list').strip()
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)

    filters = {}
    tags = re.findall(r'#(\S+)', text)
    clean = re.sub(r'#\S+', '', text).strip()

    for part in re.split(r'\s+', clean):
        if not part:
            continue
        if part.startswith('status:'):
            filters['status'] = part.split(':')[1]
        elif '.' in part:
            filters['domain'] = part
        else:
            filters['search'] = part

    async with async_session() as session:
        service = TaskService(session)
        client_service = ClientService(session)

        client_id = None
        if 'domain' in filters:
            client = await client_service.get_client_by_domain(filters['domain'])
            if client:
                client_id = client.id
        if 'search' in filters and not client_id:
            clients = await client_service.search_clients(filters['search'])
            if clients:
                client_id = clients[0].id

        tasks = await service.list_tasks(
            status=filters.get('status'),
            client_id=client_id,
        )

        if not tasks:
            await message.answer('📭 Нет задач, соответствующих фильтру.')
            return

        overdue = [t for t in tasks if t.status == 'overdue']
        today = await service.get_tasks_due_today(user_tz)
        tomorrow = await service.get_tasks_due_tomorrow(user_tz)
        today_ids = {t.id for t in today}
        tomorrow_ids = {t.id for t in tomorrow}
        other = [t for t in tasks if t.id not in today_ids and t.id not in tomorrow_ids and t.status not in ('done', 'overdue')]

        lines = []
        if overdue:
            lines.append('⚠️ <b>Просроченные:</b>')
            for t in overdue[:5]:
                dl = format_datetime(t.deadline, user_tz) if t.deadline else '?'
                c = f' [{t.client.org_name}]' if t.client else ''
                lines.append(f'  #{t.id} {t.title}{c} — {dl}')
            lines.append('')

        if today:
            lines.append('📅 <b>Сегодня:</b>')
            for t in today[:5]:
                dl = format_datetime(t.deadline, user_tz) if t.deadline else '?'
                c = f' [{t.client.org_name}]' if t.client else ''
                lines.append(f'  #{t.id} {t.title}{c} — {dl}')
            lines.append('')

        if tomorrow:
            lines.append('📅 <b>Завтра:</b>')
            for t in tomorrow[:5]:
                dl = format_datetime(t.deadline, user_tz) if t.deadline else '?'
                c = f' [{t.client.org_name}]' if t.client else ''
                lines.append(f'  #{t.id} {t.title}{c} — {dl}')
            lines.append('')

        if other:
            lines.append('📋 <b>Остальные:</b>')
            for t in other[:5]:
                dl = format_datetime(t.deadline, user_tz) if t.deadline else '?'
                c = f' [{t.client.org_name}]' if t.client else ''
                status_icon = {'todo': '⏳', 'in_progress': '🔄', 'done': '✅', 'overdue': '⚠️'}.get(t.status, '⏳')
                lines.append(f'  {status_icon} #{t.id} {t.title}{c} — {dl}')
            lines.append('')

        total = len(tasks)
        shown = min(len(overdue), 5) + min(len(today), 5) + min(len(tomorrow), 5) + min(len(other), 5)
        lines.append(f'📊 Всего: {total} задач | Показано: {shown}')

        await message.answer('\n'.join(lines), parse_mode='HTML')


@router.message(Command('done'))
async def cmd_done(message: types.Message):
    text = message.text.removeprefix('/done').strip()
    if not text or not text.isdigit():
        await message.answer('❌ Укажите ID задачи: /done 42')
        return

    task_id = int(text)
    async with async_session() as session:
        service = TaskService(session)
        task = await service.mark_done(task_id)
        if not task:
            await message.answer(f'❌ Задача #{task_id} не найдена.')
            return

        await message.answer(f'✅ Задача #{task_id} выполнена!', reply_markup=get_task_actions_keyboard(task_id))


@router.message(Command('snooze'))
async def cmd_snooze(message: types.Message, state: FSMContext):
    text = message.text.removeprefix('/snooze').strip()
    parts = text.split(maxsplit=1)
    if not parts or not parts[0].isdigit():
        await message.answer('❌ Укажите ID задачи и время. Пример: /snooze 42 +1д')
        return

    task_id = int(parts[0])
    if len(parts) > 1:
        user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
        new_deadline = parse_deadline(parts[1], user_tz)
        if not new_deadline:
            await message.answer('❌ Не удалось распознать время. Примеры: +1ч, +3д, завтра 10:00')
            return

        async with async_session() as session:
            service = TaskService(session)
            task = await service.snooze(task_id, new_deadline)
            if not task:
                await message.answer(f'❌ Задача #{task_id} не найдена.')
                return

            dl_str = format_datetime(task.deadline, user_tz)
            await message.answer(f'⏰ Задача #{task_id} отложена. Новый дедлайн: {dl_str}')
    else:
        await state.set_state(TaskStates.waiting_snooze_time)
        await state.update_data(snooze_task_id=task_id)
        await message.answer(f'⏰ На сколько отложить задачу #{task_id}? (Примеры: +1ч, +3д, завтра 10:00)')


@router.message(TaskStates.waiting_snooze_time)
async def process_snooze_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data['snooze_task_id']
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)

    new_deadline = parse_deadline(message.text, user_tz)
    if not new_deadline:
        await message.answer('❌ Не удалось распознать время. Примеры: +1ч, +3д, завтра 10:00')
        return

    async with async_session() as session:
        service = TaskService(session)
        task = await service.snooze(task_id, new_deadline)
        if not task:
            await message.answer(f'❌ Задача #{task_id} не найдена.')
            await state.clear()
            return

        dl_str = format_datetime(task.deadline, user_tz)
        await message.answer(f'⏰ Задача #{task_id} отложена. Новый дедлайн: {dl_str}')

    await state.clear()


@router.message(Command('note'))
async def cmd_note(message: types.Message):
    text = message.text.removeprefix('/note').strip()
    parts = text.split(maxsplit=1)
    if not parts or not parts[0].isdigit():
        await message.answer('❌ Укажите ID задачи и текст заметки. Пример: /note 42 Ссылка на ТЗ: https://...')
        return

    task_id = int(parts[0])
    note = parts[1] if len(parts) > 1 else ''
    if not note:
        await message.answer('❌ Введите текст заметки.')
        return

    async with async_session() as session:
        service = TaskService(session)
        task = await service.add_note(task_id, note)
        if not task:
            await message.answer(f'❌ Задача #{task_id} не найдена.')
            return

        await message.answer(f'📝 Заметка добавлена к задаче #{task_id}')


@router.callback_query(F.data.startswith('done_'))
async def cb_done(callback: types.CallbackQuery):
    task_id = int(callback.data.split('_')[1])
    async with async_session() as session:
        service = TaskService(session)
        task = await service.mark_done(task_id)
        if task:
            await callback.message.edit_text(f'✅ Задача #{task_id} выполнена!')
        else:
            await callback.message.edit_text(f'❌ Задача #{task_id} не найдена.')
    await callback.answer()


@router.callback_query(F.data.startswith('snooze_'))
async def cb_snooze(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    task_id = int(parts[1])
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)

    if len(parts) > 2:
        delta_str = parts[2]
        now = datetime.now(user_tz)
        if delta_str == '1h':
            new_deadline = now + timedelta(hours=1)
        elif delta_str == '1d':
            new_deadline = now + timedelta(days=1)
        else:
            await callback.answer('Неизвестный формат')
            return

        async with async_session() as session:
            service = TaskService(session)
            task = await service.snooze(task_id, new_deadline)
            if task:
                dl_str = format_datetime(task.deadline, user_tz)
                await callback.message.edit_text(f'⏰ Задача #{task_id} отложена. Новый дедлайн: {dl_str}')
            else:
                await callback.message.edit_text(f'❌ Задача #{task_id} не найдена.')
    else:
        await state.set_state(TaskStates.waiting_snooze_time)
        await state.update_data(snooze_task_id=task_id)
        await callback.message.answer(f'⏰ На сколько отложить задачу #{task_id}? (Примеры: +1ч, +3д, завтра 10:00)')

    await callback.answer()


@router.callback_query(F.data.startswith('note_'))
async def cb_note(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    if len(parts) < 2 or not parts[1].isdigit():
        await callback.answer('❌ Некорректный ID задачи')
        return
    task_id = int(parts[1])
    await state.set_state(TaskStates.waiting_note_text)
    await state.update_data(note_task_id=task_id)
    await callback.message.answer(f'📝 Введите текст заметки для задачи #{task_id}:')
    await callback.answer()


@router.message(TaskStates.waiting_note_text)
async def process_note_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data['note_task_id']
    note = message.text.strip()
    if not note:
        await message.answer('❌ Текст заметки не может быть пустым.')
        return

    async with async_session() as session:
        service = TaskService(session)
        task = await service.add_note(task_id, note)
        if not task:
            await message.answer(f'❌ Задача #{task_id} не найдена.')
            await state.clear()
            return

        await message.answer(f'📝 Заметка добавлена к задаче #{task_id}')

    await state.clear()


@router.callback_query(F.data == 'list_all')
async def cb_list_all(callback: types.CallbackQuery):
    await cmd_list(callback.message)
    await callback.answer()


@router.callback_query(F.data == 'add_task')
async def cb_add_task(callback: types.CallbackQuery):
    await callback.message.answer(
        '📝 Введите задачу в формате:\n'
        '<code>/add Текст задачи #тег ~дедлайн</code>\n\n'
        'Пример: <code>/add Написать статью #spbpack ~завтра 18:00</code>',
        parse_mode='HTML',
    )
    await callback.answer()
