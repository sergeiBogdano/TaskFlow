"""CRM resources are always scoped to one resolved workspace."""
from __future__ import annotations

import json
import math
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import selectinload

from app.core.database import async_session
from app.core.models import (Client, Contract, CrmActivity, CrmContact, CrmDeal, CrmField,
                             CrmPipeline, Task, User, WorkspaceMember)
from app.core.permissions import (get_accessible_client_ids, get_current_user, get_user_role_names,
                                 client_is_visible_to_user, request_permissions, resolve_workspace,
                                 task_is_visible_to_user)
from app.core.utils.timezone import safe_dt, utc_now

router = APIRouter(prefix='/api/crm', tags=['crm'])


class Payload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Stage(Payload):
    id: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    label: str = Field(min_length=1, max_length=100)
    outcome: Literal['open', 'won', 'lost'] = 'open'


class PipelinePayload(Payload):
    name: str = Field(min_length=1, max_length=120)
    stages: list[Stage] = Field(min_length=1, max_length=30)


class ContactPayload(Payload):
    name: str = Field(min_length=1, max_length=200)
    client_id: int | None = None
    email: str = Field(default='', max_length=200)
    phone: str = Field(default='', max_length=80)
    position: str = Field(default='', max_length=160)


class DealPayload(Payload):
    title: str = Field(min_length=1, max_length=200)
    pipeline_id: int
    stage: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(default=Decimal('0'), ge=0, max_digits=16, decimal_places=2)
    currency: str = Field(default='RUB', pattern=r'^[A-Z]{3}$')
    client_id: int | None = None
    contact_id: int | None = None
    contract_id: int | None = None
    task_id: int | None = None
    assignee_id: int | None = None
    custom_fields: dict = Field(default_factory=dict)
    notes: str = Field(default='', max_length=10000)
    archived: bool = False


class ActivityPayload(Payload):
    deal_id: int
    title: str = Field(min_length=1, max_length=300)
    kind: Literal['task', 'call', 'meeting', 'note'] = 'task'
    due_at: datetime | None = None
    completed: bool = False


class FieldPayload(Payload):
    key: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9_]*$')
    label: str = Field(min_length=1, max_length=120)
    kind: Literal['text', 'number', 'date', 'checkbox'] = 'text'
    required: bool = False
    position: int = Field(default=0, ge=0, le=1000)


RESOURCES = {
    'pipelines': (CrmPipeline, PipelinePayload), 'contacts': (CrmContact, ContactPayload),
    'deals': (CrmDeal, DealPayload), 'activities': (CrmActivity, ActivityPayload),
    'fields': (CrmField, FieldPayload),
}


def resource(kind):
    if kind not in RESOURCES:
        raise HTTPException(status_code=404, detail='Раздел CRM не найден')
    return RESOURCES[kind]


def encode(row):
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = str(value)
        elif column.name in ('stages', 'custom_fields'):
            value = json.loads(value)
        result[column.name] = value
    return result


async def context(session, request, user, action='crm'):
    roles = await get_user_role_names(user.id)
    from app.core.permissions import workspace_id_from_request
    ws, _ = await resolve_workspace(session, user, roles, workspace_id_from_request(request))
    permissions = await request_permissions(user, ws.id)
    if not (permissions.get('all') or permissions.get(action)):
        raise HTTPException(status_code=403, detail=f'Нет права: {action}')
    from app.core.permissions import is_feature_available
    if not await is_feature_available(user, action, ws.id):
        raise HTTPException(status_code=403, detail=f'Функция отключена: {action}')
    return ws, roles, permissions


async def scoped(session, model, ident, ws_id):
    row = await session.get(model, ident)
    if not row or row.workspace_id != ws_id:
        raise HTTPException(status_code=404, detail='Объект не найден в этом пространстве')
    return row


async def validate_links(session, kind, data, ws, user, roles, permissions, row=None):
    accessible = await get_accessible_client_ids(session, user.id, roles)
    client = None
    if data.get('client_id'):
        client = await scoped(session, Client, data['client_id'], ws.id)
        if client.deleted_at or not client_is_visible_to_user(client.id, roles, accessible):
            raise HTTPException(status_code=403, detail='Нет доступа к клиенту')
    if kind == 'deals':
        pipeline = await scoped(session, CrmPipeline, data['pipeline_id'], ws.id)
        if data['stage'] not in {stage['id'] for stage in json.loads(pipeline.stages)}:
            raise HTTPException(status_code=400, detail='Этап отсутствует в выбранной воронке')
        if data.get('contact_id'):
            contact = await scoped(session, CrmContact, data['contact_id'], ws.id)
            if contact.deleted_at or (contact.client_id and contact.client_id != data.get('client_id')):
                raise HTTPException(status_code=400, detail='Контакт не принадлежит выбранному клиенту')
        if data.get('contract_id'):
            contract = await session.get(Contract, data['contract_id'])
            if not client or not contract or contract.client_id != client.id:
                raise HTTPException(status_code=400, detail='Договор не принадлежит выбранному клиенту')
            if not (permissions.get('all') or permissions.get('client_tab_contracts')):
                raise HTTPException(status_code=403, detail='Нет доступа к договорам')
        if data.get('task_id'):
            task = await scoped(session, Task, data['task_id'], ws.id)
            if task.deleted_at or not task_is_visible_to_user(task, user, roles, accessible, permissions):
                raise HTTPException(status_code=403, detail='Нет доступа к задаче')
            if task.client_id and task.client_id != data.get('client_id'):
                raise HTTPException(status_code=400, detail='Задача относится к другому клиенту')
        if data.get('assignee_id'):
            membership = (await session.execute(select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == data['assignee_id']))).scalars().first()
            account = await session.get(User, data['assignee_id'])
            if not membership or not account or not account.is_active:
                raise HTTPException(status_code=400, detail='Ответственный должен быть активным участником пространства')
        fields = (await session.execute(select(CrmField).where(CrmField.workspace_id == ws.id))).scalars().all()
        values = data.get('custom_fields', {})
        known = {f.key for f in fields}
        if set(values) - known:
            raise HTTPException(status_code=400, detail='Неизвестное дополнительное поле')
        for field in fields:
            value = values.get(field.key)
            if field.required and (value is None or value == ''):
                raise HTTPException(status_code=400, detail=f'Заполните поле: {field.label}')
            if value is None or value == '':
                continue
            valid = ((field.kind == 'text' and isinstance(value, str) and len(value) <= 2000)
                     or (field.kind == 'number' and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value))
                     or (field.kind == 'checkbox' and isinstance(value, bool)))
            if field.kind == 'date' and isinstance(value, str):
                try:
                    datetime.strptime(value, '%Y-%m-%d')
                    valid = True
                except ValueError:
                    pass
            if not valid:
                raise HTTPException(status_code=400, detail=f'Неверный тип поля: {field.label}')
        data['custom_fields'] = json.dumps(values, ensure_ascii=False, allow_nan=False)
    if kind == 'activities':
        deal = await scoped(session, CrmDeal, data['deal_id'], ws.id)
        if deal.deleted_at:
            raise HTTPException(status_code=400, detail='Сделка удалена')
    if kind == 'pipelines':
        stages = data['stages']
        if len({s['id'] for s in stages}) != len(stages):
            raise HTTPException(status_code=400, detail='Идентификаторы этапов должны быть уникальны')
        if row:
            used = (await session.execute(select(CrmDeal.stage).where(CrmDeal.pipeline_id == row.id))).scalars().all()
            if set(used) - {s['id'] for s in stages}:
                raise HTTPException(status_code=409, detail='Сначала перенесите сделки с удаляемых этапов')
        data['stages'] = json.dumps(stages, ensure_ascii=False)
    if kind == 'fields':
        existing = (await session.execute(select(CrmField).where(CrmField.workspace_id == ws.id, CrmField.key == data['key']))).scalars().first()
        if existing and (not row or existing.id != row.id):
            raise HTTPException(status_code=409, detail='Ключ поля уже существует')
        if row and (data['key'] != row.key or data['kind'] != row.kind):
            raise HTTPException(status_code=400, detail='Ключ и тип существующего поля неизменяемы')
    return data


@router.get('/{kind}')
async def list_resources(kind: str, request: Request, archived: bool = False, deleted: bool = False,
                         limit: int = Query(500, ge=1, le=1000), user=Depends(get_current_user)):
    model, _ = resource(kind)
    async with async_session() as session:
        ws, _, _ = await context(session, request, user)
        stmt = select(model).where(model.workspace_id == ws.id)
        if hasattr(model, 'deleted_at'):
            stmt = stmt.where(model.deleted_at.is_not(None) if deleted else model.deleted_at.is_(None))
        if kind == 'deals' and not deleted:
            stmt = stmt.where(model.archived == archived)
        rows = (await session.execute(stmt.order_by(model.id).limit(limit))).scalars().all()
        result = [encode(row) for row in rows]
        if kind == 'fields':
            result.sort(key=lambda item: (item['position'], item['id']))
        return result


@router.post('/{kind}', status_code=201)
async def create_resource(kind: str, request: Request, user=Depends(get_current_user)):
    model, schema = resource(kind)
    try:
        data = schema.model_validate(await request.json()).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc
    async with async_session() as session:
        action = 'crm_configure' if kind in ('pipelines', 'fields') else 'crm_edit'
        ws, roles, permissions = await context(session, request, user, action)
        data = await validate_links(session, kind, data, ws, user, roles, permissions)
        if kind == 'activities':
            data['created_by'] = user.id
        row = model(workspace_id=ws.id, **data)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return encode(row)


@router.patch('/{kind}/{ident}')
async def update_resource(kind: str, ident: int, request: Request, user=Depends(get_current_user)):
    model, schema = resource(kind)
    patch = await request.json()
    if not isinstance(patch, dict) or set(patch) - set(schema.model_fields):
        raise HTTPException(status_code=400, detail='Неизвестное поле')
    async with async_session() as session:
        action = 'crm_configure' if kind in ('pipelines', 'fields') else 'crm_edit'
        ws, roles, permissions = await context(session, request, user, action)
        row = await scoped(session, model, ident, ws.id)
        if getattr(row, 'deleted_at', None):
            raise HTTPException(status_code=409, detail='Сначала восстановите объект')
        current = encode(row)
        try:
            data = schema.model_validate({**{k: current.get(k) for k in schema.model_fields}, **patch}).model_dump()
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc
        data = await validate_links(session, kind, data, ws, user, roles, permissions, row)
        for key, value in data.items():
            setattr(row, key, value)
        await session.commit()
        await session.refresh(row)
        return encode(row)


@router.delete('/{kind}/{ident}')
async def delete_resource(kind: str, ident: int, request: Request, permanent: bool = False, user=Depends(get_current_user)):
    model, _ = resource(kind)
    async with async_session() as session:
        ws, _, _ = await context(session, request, user, 'crm_configure' if kind in ('pipelines', 'fields') else 'crm_delete')
        row = await scoped(session, model, ident, ws.id)
        if kind == 'pipelines':
            used = (await session.execute(select(CrmDeal.id).where(CrmDeal.pipeline_id == ident))).scalars().first()
            if used:
                raise HTTPException(status_code=409, detail='Воронка содержит сделки')
        if kind == 'fields':
            deals = (await session.execute(select(CrmDeal).where(CrmDeal.workspace_id == ws.id))).scalars().all()
            for deal in deals:
                values = json.loads(deal.custom_fields)
                values.pop(row.key, None)
                deal.custom_fields = json.dumps(values, ensure_ascii=False)
        if hasattr(row, 'deleted_at') and not permanent:
            row.deleted_at = utc_now()
        else:
            if kind == 'deals':
                await session.execute(delete(CrmActivity).where(CrmActivity.deal_id == ident))
                await session.execute(update(Task).where(Task.crm_deal_id == ident).values(crm_deal_id=None))
            if kind == 'contacts':
                await session.execute(update(CrmDeal).where(CrmDeal.contact_id == ident).values(contact_id=None))
            await session.delete(row)
        await session.commit()
    return {'ok': True}


@router.post('/{kind}/{ident}/restore')
async def restore_resource(kind: str, ident: int, request: Request, user=Depends(get_current_user)):
    model, _ = resource(kind)
    if not hasattr(model, 'deleted_at'):
        raise HTTPException(status_code=400, detail='Объект не поддерживает корзину')
    async with async_session() as session:
        ws, _, _ = await context(session, request, user, 'crm_delete')
        row = await scoped(session, model, ident, ws.id)
        row.deleted_at = None
        await session.commit()
    return {'ok': True}


class RenewalPayload(Payload):
    end_date: datetime
    create_task: bool = True


@router.post('/contracts/{ident}/renew')
async def renew_contract(ident: int, request: Request, user=Depends(get_current_user)):
    try:
        body = RenewalPayload.model_validate(await request.json())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc
    async with async_session() as session:
        ws, roles, permissions = await context(session, request, user, 'crm_edit')
        if not (permissions.get('all') or permissions.get('client_tab_contracts')):
            raise HTTPException(status_code=403, detail='Нет доступа к договорам')
        contract = await session.get(Contract, ident)
        if not contract:
            raise HTTPException(status_code=404, detail='Договор не найден')
        client = await scoped(session, Client, contract.client_id, ws.id)
        accessible = await get_accessible_client_ids(session, user.id, roles)
        if client.deleted_at or not client_is_visible_to_user(client.id, roles, accessible):
            raise HTTPException(status_code=403, detail='Нет доступа к клиенту')
        end = safe_dt(body.end_date)
        if end < safe_dt(contract.start_date):
            raise HTTPException(status_code=400, detail='Окончание договора не может быть раньше начала')
        if contract.end_date and end <= safe_dt(contract.end_date):
            raise HTTPException(status_code=400, detail='Новая дата должна быть позже текущей')
        contract.end_date = end.replace(tzinfo=None)
        contract.status = 'active'
        if not client.contract_end or end > safe_dt(client.contract_end):
            client.contract_end = end
        task = None
        if body.create_task:
            from app.core.permissions import is_feature_available
            if not await is_feature_available(user, 'tasks', ws.id):
                raise HTTPException(status_code=403, detail='Модуль задач отключён')
            if not (permissions.get('all') or permissions.get('tasks')):
                raise HTTPException(status_code=403, detail='Нет права создавать задачу')
            actor_member = (await session.execute(select(WorkspaceMember.id).where(WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == user.id))).scalar_one_or_none()
            task = Task(workspace_id=ws.id, client_id=client.id, contract_id=contract.id, title=f'Продление договора: {client.org_name}',
                        deadline=end, creator_id=user.id, assignee_id=user.id if actor_member else None, status='todo')
            session.add(task)
            await session.flush()
            linked = (await session.execute(select(CrmDeal).where(CrmDeal.workspace_id == ws.id, CrmDeal.contract_id == ident))).scalars().all()
            for deal in linked:
                deal.task_id = task.id
        await session.commit()
        return {'ok': True, 'task_id': task.id if task else None, 'end_date': end.isoformat()}


class DealTaskPayload(Payload):
    title: str = Field(min_length=1, max_length=200)
    deadline: datetime | None = None
    assignee_id: int | None = None


@router.get('/deals/{ident}/tasks')
async def deal_tasks(ident: int, request: Request, user=Depends(get_current_user)):
    async with async_session() as session:
        ws, roles, permissions = await context(session, request, user)
        deal = await scoped(session, CrmDeal, ident, ws.id)
        from app.core.permissions import is_feature_available
        if not (permissions.get('all') or permissions.get('tasks')) or not await is_feature_available(user, 'tasks', ws.id):
            raise HTTPException(status_code=403, detail='Нет доступа к задачам')
        accessible = await get_accessible_client_ids(session, user.id, roles)
        rows = (await session.execute(select(Task).options(selectinload(Task.co_executor_links)).where(
            Task.workspace_id == ws.id, Task.deleted_at.is_(None),
            or_(Task.crm_deal_id == ident, Task.id == deal.task_id, Task.contract_id == deal.contract_id if deal.contract_id else False)
        ).order_by(Task.id.desc()))).scalars().all()
        return [{'id': t.id, 'title': t.title, 'status': t.status, 'contract_id': t.contract_id,
                 'deadline': t.deadline.isoformat() if t.deadline else None} for t in rows
                if task_is_visible_to_user(t, user, roles, accessible, permissions)]


@router.post('/deals/{ident}/tasks', status_code=201)
async def create_deal_task(ident: int, request: Request, user=Depends(get_current_user)):
    try:
        body = DealTaskPayload.model_validate(await request.json())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc
    async with async_session() as session:
        ws, roles, permissions = await context(session, request, user, 'crm_edit')
        deal = await scoped(session, CrmDeal, ident, ws.id)
        if deal.deleted_at or deal.archived:
            raise HTTPException(status_code=409, detail='Сначала верните сделку в работу')
        from app.core.permissions import is_feature_available
        if not (permissions.get('all') or permissions.get('tasks')) or not await is_feature_available(user, 'tasks', ws.id):
            raise HTTPException(status_code=403, detail='Нет права создавать задачи')
        if body.assignee_id:
            member = (await session.execute(select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == body.assignee_id))).scalar_one_or_none()
            account = await session.get(User, body.assignee_id)
            if not member or not account or not account.is_active:
                raise HTTPException(status_code=400, detail='Исполнитель должен быть активным участником пространства')
        if deal.client_id:
            client = await scoped(session, Client, deal.client_id, ws.id)
            if client.deleted_at:
                raise HTTPException(status_code=409, detail='Сначала восстановите организацию')
        if deal.contract_id:
            if not (permissions.get('all') or permissions.get('client_tab_contracts')):
                raise HTTPException(status_code=403, detail='Нет доступа к договорам')
            contract = await session.get(Contract, deal.contract_id)
            if not contract or contract.client_id != deal.client_id:
                raise HTTPException(status_code=409, detail='Связанный договор недоступен')
            if body.deadline and safe_dt(body.deadline) > safe_dt(contract.end_date):
                raise HTTPException(status_code=400, detail='Срок задачи позже окончания договора')
        task = Task(workspace_id=ws.id, crm_deal_id=deal.id, client_id=deal.client_id,
                    contract_id=deal.contract_id, creator_id=user.id, assignee_id=body.assignee_id,
                    title=body.title, deadline=safe_dt(body.deadline) if body.deadline else None, status='todo')
        session.add(task)
        await session.flush()
        deal.task_id = task.id
        await session.commit()
        return {'id': task.id, 'title': task.title, 'status': task.status, 'contract_id': task.contract_id}
