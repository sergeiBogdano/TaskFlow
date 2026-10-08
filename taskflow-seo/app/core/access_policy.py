"""Workspace profiles plus explicit personal exceptions; UI visibility is separate."""
import json
from contextvars import ContextVar

from fastapi import HTTPException
from sqlalchemy import select

from app.core.database import async_session
from app.core.models import WorkspaceMember, WorkspaceRole

FIELD_CATALOG = {
    'tasks': {
        'title': ('Название', ('title',)), 'status': ('Статус', ('status',)),
        'priority': ('Приоритет', ('priority',)), 'taskType': ('Тип', ('task_type',)),
        'client': ('Клиент', ('client_id', 'client', 'client_warning', 'contract_id', 'crm_deal_id', 'client_access_ids')),
        'assignee': ('Исполнитель', ('assignee_id',)),
        'coExecutors': ('Соисполнители', ('co_executor_id', 'co_executor_ids')),
        'completionDate': ('Дата выполнения', ('completion_date',)),
        'deadline': ('Крайний срок', ('deadline',)), 'visibility': ('Видимость', ('visibility',)),
        'noContract': ('Нет договора', ('no_contract',)), 'notes': ('Описание', ('notes',)),
        'comment': ('Выполненные работы', ('comment',)), 'sprint': ('Спринт', ('sprint_ids',)),
    },
    'sprints': {
        'name': ('Название', ('name',)), 'goal': ('Цель', ('goal',)),
        'start': ('Начало', ('start_date',)), 'end': ('Конец', ('end_date',)),
    },
}
# Compatibility set is frozen: adding a future field to the catalogue does not grant it.
LEGACY_FIELDS = {
    'tasks': frozenset(('title', 'status', 'priority', 'taskType', 'client', 'assignee', 'coExecutors',
                       'completionDate', 'deadline', 'visibility', 'noContract', 'notes', 'comment', 'sprint')),
    'sprints': frozenset(('name', 'goal', 'start', 'end')),
}
MODES = {'hidden': 0, 'view': 1, 'edit': 2}
_FIELDS = ContextVar('request_field_access', default={})


def parse_policy(raw):
    value = json.loads(raw or '{}') if isinstance(raw, str) else raw or {}
    return value if isinstance(value, dict) else {}


def validate_fields(raw):
    if not isinstance(raw, dict):
        raise HTTPException(400, 'Настройки полей должны быть объектом')
    for entity, fields in raw.items():
        if entity not in FIELD_CATALOG or not isinstance(fields, dict):
            raise HTTPException(400, 'Неизвестный раздел полей')
        for key, mode in fields.items():
            if key not in FIELD_CATALOG[entity] or not isinstance(mode, str) or mode not in MODES:
                raise HTTPException(400, 'Неизвестное поле или режим доступа')
            if (entity, key) in (('tasks', 'title'), ('tasks', 'status'), ('sprints', 'name')) and mode == 'hidden':
                raise HTTPException(400, 'Название и статус нужны для работы: можно оставить только просмотр')
    return raw


async def field_access(user, workspace_id):
    fields = {entity: {key: 'edit' if key in LEGACY_FIELDS[entity] else 'hidden' for key in values}
              for entity, values in FIELD_CATALOG.items()}
    if user.is_root or not workspace_id:
        return fields
    async with async_session() as session:
        member = (await session.execute(select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id))).scalar_one_or_none()
        if not member:
            return {entity: {key: 'hidden' for key in values} for entity, values in fields.items()}
        role = await session.get(WorkspaceRole, member.custom_role_id) if member.custom_role_id else None
        if member.custom_role_id and (not role or role.deleted_at or role.workspace_id != workspace_id):
            return {entity: {key: 'hidden' for key in values} for entity, values in fields.items()}
        profile = parse_policy(role.field_access) if role and role.workspace_id == workspace_id else {}
        personal = parse_policy(member.access_overrides).get('fields', {})
        for policy in (profile, personal):
            for entity, values in policy.items():
                if entity in fields:
                    fields[entity].update({key: mode for key, mode in values.items()
                                           if key in fields[entity] and mode in MODES})
    return fields


def set_field_context(fields):
    return _FIELDS.set(fields)


def reset_field_context(token):
    _FIELDS.reset(token)


def redact_fields(entity, data):
    out = dict(data)
    for key, mode in _FIELDS.get().get(entity, {}).items():
        if mode == 'hidden':
            for alias in FIELD_CATALOG[entity][key][1]:
                out.pop(alias, None)
    return out


def assert_field_writes(entity, data, current=None):
    for key, mode in _FIELDS.get().get(entity, {}).items():
        if mode == 'edit':
            continue
        for alias in FIELD_CATALOG[entity][key][1]:
            if alias not in data:
                continue
            # Full-form clients may echo unchanged read-only values; changes never pass.
            old = getattr(current, alias, None) if current else None
            if current is not None and data[alias] == old:
                continue
            raise HTTPException(403, f'Поле «{FIELD_CATALOG[entity][key][0]}»: редактирование запрещено')


async def assert_field_ceiling(actor, workspace_id, proposed, baseline=None):
    if actor.is_root:
        return
    ceiling = await field_access(actor, workspace_id)
    candidate = {entity: {key: 'edit' if key in LEGACY_FIELDS[entity] else 'hidden' for key in values}
                 for entity, values in FIELD_CATALOG.items()} if baseline is None else {entity: dict(values) for entity, values in baseline.items()}
    for entity, values in proposed.items():
        candidate[entity].update(values)
    for entity, values in candidate.items():
        for key, mode in values.items():
            if MODES[mode] > MODES[ceiling[entity][key]]:
                raise HTTPException(403, 'Нельзя выдать доступ к полю шире собственного')


def field_catalog_payload():
    return {entity: {key: {'label': value[0], 'required': (entity, key) in
                         (('tasks', 'title'), ('tasks', 'status'), ('sprints', 'name'))}
                     for key, value in fields.items()} for entity, fields in FIELD_CATALOG.items()}


def redact_nested_fields(value):
    if isinstance(value, list):
        return [redact_nested_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    if 'title' in value and ('status' in value or 'task_type' in value):
        value = redact_fields('tasks', value)
    elif 'name' in value and ('start_date' in value or 'end_date' in value):
        value = redact_fields('sprints', value)
    return {key: redact_nested_fields(item) for key, item in value.items()}


def field_is_visible(entity, key):
    return _FIELDS.get().get(entity, {}).get(key, 'edit') != 'hidden'
