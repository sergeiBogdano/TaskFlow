"""Authenticate every API request and enforce permissions in the object's actual space.

Work permissions come exclusively from membership; platform permissions cannot bypass
space roles. Disabled modules block root as well. Root retains emergency access to
individual feature switches, while normal users respect global disable limits.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.auth import COOKIE_NAME, verify_session_token, session_matches_user
from app.core.permissions import (
    effective_permissions,
    get_workspace_permissions,
    is_feature_available,
    set_request_permissions,
    workspace_id_from_request,
)

# префикс API → обязательный work-ключ
API_PREFIX_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ('/api/crm', 'crm'),
    ('/api/quick-tasks', 'tasks'),
    ('/api/templates', 'tasks'),
    ('/api/tasks', 'tasks'),
    ('/api/sprints', 'kanban'),
    ('/api/calendar', 'calendar'),
    ('/api/dashboard', 'dashboard'),
    ('/api/clients', 'clients'),
    ('/api/reports', 'reports'),
    ('/api/notifications', 'notifications'),
    ('/api/modules', 'modules'),
    ('/api/notes', 'notes'),
    ('/api/ai', 'ai'),
)

# пути вне проверки (плюс всё, что не /api/ и не в таблице выше)
_SKIP_PREFIXES = ('/api/auth', '/api/search', '/api/activity', '/api/files',
                  '/api/saved-views', '/api/permissions')

# публичные API-точки: работают без сессии (вход/выход/проверка сессии).
# Всё остальное /api/* без валидной сессии получает 401 здесь — это закрывает
# и legacy-роуты (TASKFLOW_LEGACY_UI), которые сами авторизацию не делают.
PUBLIC_API_PREFIXES: tuple[str, ...] = ('/api/auth',)


def required_permission(path: str, method: str) -> str | None:
    """Какой work-ключ нужен запросу. None — проверять нечего."""
    if not path.startswith('/api/'):
        return None
    for prefix in _SKIP_PREFIXES:
        if path == prefix or path.startswith(prefix + '/'):
            return None
    if path == '/api/workspaces' and method == 'POST':
        # создание своего окружения доступно любому вошедшему:
        # право тут не нужно, лимит (3) проверяет сам эндпоинт
        return None
    if path.startswith('/api/workspaces'):
        # чтение окружения открыто участникам (переключатель, справочники),
        # управление окружением — только с правом «workspace»
        return None  # Membership/rank dependencies guard management, independently of work roles.
    if path in ('/api/dashboard/organizations', '/api/dashboard/expiring', '/api/dashboard/clients'):
        return 'clients'
    for prefix, key in API_PREFIX_PERMISSIONS:
        if path == prefix or path.startswith(prefix + '/'):
            return key
    return None


async def work_permission_middleware(request: Request, call_next):
    path, method = request.url.path, request.method
    if not path.startswith('/api/'):
        return await call_next(request)
    is_public = path.startswith(PUBLIC_API_PREFIXES)
    token = request.cookies.get(COOKIE_NAME)
    user_id = verify_session_token(token) if token else None
    if user_id is None:
        if is_public:
            return await call_next(request)
        return JSONResponse({'detail': 'Not authenticated'}, status_code=401)
    from app.services.user_service import get_user
    user = await get_user(user_id)
    if not session_matches_user(token or '', user):
        if is_public:
            return await call_next(request)
        return JSONResponse({'detail': 'Not authenticated'}, status_code=401)
    if user.must_change_password and path not in ('/api/auth/me', '/api/auth/logout', '/api/users/change-password'):
        return JSONResponse({'detail': 'Сначала смените временный пароль', 'code': 'password_change_required'}, status_code=403)
    workspace_id = workspace_id_from_request(request)
    # Object routes must use the object's space, never privileges from a query-selected space.
    segments = path.strip('/').split('/')
    if len(segments) >= 3 and segments[0] == 'api' and segments[2].isdigit():
        from app.core import models
        object_models = {'tasks': models.Task, 'clients': models.Client, 'notes': models.Note,
                         'calendar': models.Task, 'sprints': models.Sprint, 'modules': models.Module, 'reports': models.GeneratedReport}
        model = object_models.get(segments[1])
        if model is not None:
            from app.core.database import async_session
            async with async_session() as session:
                obj = await session.get(model, int(segments[2]))
                actual = getattr(obj, 'workspace_id', None) if obj else None
                if segments[1] == 'reports' and obj and obj.client_id:
                    client = await session.get(models.Client, obj.client_id)
                    actual = client.workspace_id if client else None
            if actual is not None:
                if workspace_id is not None and workspace_id != actual:
                    return JSONResponse({'detail': 'Объект не найден в выбранном пространстве'}, status_code=404)
                workspace_id = actual
    # Resolve the default space before permission checks, including requests without query params.
    key = required_permission(path, method)
    if key and not path.startswith('/api/workspaces'):
        from app.core.database import async_session
        from app.core.permissions import get_user_role_names, resolve_workspace
        from fastapi import HTTPException
        try:
            async with async_session() as session:
                space, _ = await resolve_workspace(session, user, await get_user_role_names(user.id), workspace_id)
                workspace_id = space.id
        except HTTPException as exc:
            return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    request.state.workspace_id = workspace_id
    permissions = await effective_permissions(user, workspace_id)
    # один набор прав на весь запрос: эндпоинты читают через request_permissions()
    set_request_permissions(user.id, permissions)
    key = required_permission(path, method)
    action = None
    if path.startswith('/api/tasks') and method != 'GET':
        if path == '/api/tasks' and method == 'POST':
            action = 'tasks_create'
        elif method == 'DELETE' or path.endswith('/restore') or path.endswith('/clear-trash'):
            action = 'tasks_delete'
        else:
            action = 'tasks_edit'
    if path.startswith('/api/calendar') and method != 'GET':
        action = 'tasks_edit'
    if path.startswith('/api/sprints') and method != 'GET':
        action = 'sprints_plan'
    if action and not permissions.get('all') and not (permissions.get(action) and await is_feature_available(user, action, workspace_id)):
        return JSONResponse({'detail': 'Нет разрешения на действие: ' + action}, status_code=403)
    if key and not (permissions.get('all') or permissions.get(key)):
        return JSONResponse({'detail': f'Нет права доступа: {key}'}, status_code=403)
    if key and workspace_id is not None and not permissions.get('all'):
        # явное окружение: право считается по членству в нём (Ф8);
        # не участник — доступ отклонит сам эндпоинт («Нет доступа к воркспейсу»)
        ws_perms = await get_workspace_permissions(user.id, workspace_id)
        if ws_perms is not None and not ws_perms.get(key):
            return JSONResponse({'detail': f'Нет права доступа: {key}'}, status_code=403)
    # без указания окружения work-право проверяет эндпоинт: app-права (legacy)
    # и его внятные сообщения («нет окружения», «Нет доступа к воркспейсу»)
    if key and not await is_feature_available(user, key, workspace_id):
        return JSONResponse({'detail': f'Функция "{key}" отключена краном доступности'}, status_code=403)
    from app.core.access_policy import field_access, set_field_context, reset_field_context
    fields = await field_access(user, workspace_id)
    # Reports/AI and templates can copy restricted task fields to unstructured text.
    # Require a full field view before giving access to those derived outputs.
    has_hidden = any(mode == 'hidden' for values in fields.values() for mode in values.values())
    if has_hidden and any(path.startswith(prefix) for prefix in
                          ('/api/ai', '/api/reports', '/api/modules', '/api/quick-tasks', '/api/templates', '/api/activity', '/api/search', '/api/dashboard')):
        return JSONResponse({'detail': 'Раздел формирует данные из скрытых полей. Требуется профиль без скрытых полей.'}, status_code=403)
    if has_hidden and (path.endswith('/activity') or path.endswith('/export')):
        return JSONResponse({'detail': 'История и выгрузки требуют просмотра всех полей'}, status_code=403)
    if path.startswith('/api/calendar') and any(fields['tasks'][key] == 'hidden' for key in ('deadline', 'completionDate', 'assignee', 'client')):
        return JSONResponse({'detail': 'Календарь требует просмотра сроков, исполнителя и клиента'}, status_code=403)
    if path.startswith('/api/tasks') and method == 'GET':
        query_fields = {'client': ('client', 'client_id'), 'assignee': ('assignee', 'scope_user_id'), 'priority': ('priority',), 'taskType': ('task_type',),
                        'sprint': ('sprint', 'sprint_id'), 'deadline': ('date_from', 'date_to')}
        for field, params in query_fields.items():
            if fields['tasks'][field] == 'hidden' and any(request.query_params.get(param) for param in params):
                return JSONResponse({'detail': 'Нельзя фильтровать по скрытому полю'}, status_code=403)
    token = set_field_context(fields)
    try:
        response = await call_next(request)
        if response.status_code < 400 and 'application/json' in response.headers.get('content-type', ''):
            import json
            from app.core.access_policy import redact_nested_fields
            body = b''.join([chunk async for chunk in response.body_iterator])
            from app.core.rich_text import clean_payload
            value = clean_payload(redact_nested_fields(json.loads(body)))
            headers = {key: value for key, value in response.headers.items() if key not in ('content-length', 'content-type')}
            return JSONResponse(value, status_code=response.status_code, headers=headers, background=response.background)
        return response
    finally:
        reset_field_context(token)
