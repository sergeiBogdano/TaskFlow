from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.core.database import async_session
from app.core.utils.timezone import utc_now, to_user_tz, to_utc, format_datetime, parse_deadline
from app.core.utils.validators import validate_date
from app.core.config import settings
from app.services.client_service import ClientService
from app.services.task_service import TaskService
from app.services.template_service import TemplateService
from app.bot.keyboards import get_template_keyboard, get_task_actions_keyboard

router = Router()


class ClientStates(StatesGroup):
    waiting_org_name = State()
    waiting_domain = State()
    waiting_contract_start = State()
    waiting_contract_end = State()
    waiting_template = State()


@router.message(Command('new_client'))
async def cmd_new_client(message: types.Message, state: FSMContext):
    await state.set_state(ClientStates.waiting_org_name)
    await message.answer('📛 Введите название организации:')


@router.message(ClientStates.waiting_org_name)
async def process_org_name(message: types.Message, state: FSMContext):
    await state.update_data(org_name=message.text.strip())
    await state.set_state(ClientStates.waiting_domain)
    await message.answer('🌐 Введите домен (опционально):')


@router.message(ClientStates.waiting_domain)
async def process_domain(message: types.Message, state: FSMContext):
    domain = message.text.strip() or None
    await state.update_data(domain=domain)
    await state.set_state(ClientStates.waiting_contract_start)
    await message.answer('📅 Дата начала договора (ДД.ММ.ГГГГ):')


@router.message(ClientStates.waiting_contract_start)
async def process_contract_start(message: types.Message, state: FSMContext):
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    dt = parse_deadline(message.text.strip(), user_tz)
    if not dt:
        await message.answer('❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ (например 01.06.2024)')
        return
    await state.update_data(contract_start=dt)
    await state.set_state(ClientStates.waiting_contract_end)
    await message.answer('📅 Дата окончания договора (ДД.ММ.ГГГГ):')


@router.message(ClientStates.waiting_contract_end)
async def process_contract_end(message: types.Message, state: FSMContext):
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)
    dt = parse_deadline(message.text.strip(), user_tz)
    if not dt:
        await message.answer('❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ (например 01.12.2024)')
        return

    data = await state.get_data()
    contract_start = data['contract_start']

    if dt <= contract_start:
        await message.answer('❌ Дата окончания должна быть позже даты начала.')
        return

    await state.update_data(contract_end=dt)
    await state.set_state(ClientStates.waiting_template)
    await message.answer('📦 Выберите шаблон проекта:', reply_markup=get_template_keyboard())


@router.callback_query(F.data.startswith('template_'))
async def process_template_choice(callback: types.CallbackQuery, state: FSMContext):
    template_name = callback.data.replace('template_', '')
    data = await state.get_data()
    user_tz = ZoneInfo(settings.DEFAULT_TIMEZONE)

    async with async_session() as session:
        client_service = ClientService(session)
        task_service = TaskService(session)
        template_service = TemplateService()

        client = await client_service.create_client(
            org_name=data['org_name'],
            domain=data.get('domain'),
            contract_start=data['contract_start'],
            contract_end=data['contract_end'],
        )

        tasks_created = 0
        if template_name != 'empty':
            template_tasks = template_service.generate_tasks(
                template_name=template_name,
                contract_start=data['contract_start'],
                user_tz=user_tz,
            )
            for task_data in template_tasks:
                await task_service.create_task(
                    title=task_data['title'],
                    client_id=client.id,
                    task_type=task_data.get('task_type', 'custom'),
                    deadline=task_data.get('deadline'),
                    priority=task_data.get('priority', 'medium'),
                    checklist=task_data.get('checklist'),
                )
                tasks_created += 1

        end_str = format_datetime(client.contract_end, user_tz)
        await callback.message.edit_text(
            f'✅ Клиент "{client.org_name}" создан.\n'
            f'Сгенерировано задач: {tasks_created}\n'
            f'🔔 Напомню за 14 дней до {end_str}.'
        )

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == 'new_client')
async def cb_new_client(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cmd_new_client(callback.message, state)
    await callback.answer()


@router.callback_query(F.data.startswith('extend_'))
async def cb_extend_contract(callback: types.CallbackQuery):
    client_id = int(callback.data.split('_')[1])
    await callback.message.answer(
        f'📅 Для продления договора клиента #{client_id} используйте /new_client '
        f'или обратитесь к веб-интерфейсу (v2.0).'
    )
    await callback.answer()


@router.callback_query(F.data.startswith('client_tasks_'))
async def cb_client_tasks(callback: types.CallbackQuery):
    client_id = int(callback.data.split('_')[2])
    async with async_session() as session:
        service = TaskService(session)
        tasks = await service.get_active_client_tasks(client_id)
        if not tasks:
            await callback.message.answer('📭 Нет активных задач.')
        else:
            lines = ['📋 <b>Активные задачи:</b>']
            for t in tasks:
                lines.append(f'  #{t.id} {t.title} — {t.status}')
            await callback.message.answer('\n'.join(lines), parse_mode='HTML')
    await callback.answer()
