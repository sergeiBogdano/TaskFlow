"""Проверка work-прав на уровне API (Ф8).

Карта путей → ключ scope=work. Effective-права считаются по активному
окружению (база по rank + кастомная роль), при отсутствии окружения —
app-права, как раньше. Закрытая краном функция тоже даёт 403.

Work-ключ из карты применяется только при явном окружении (path
/api/workspaces/{id}/… или query workspace_id) и членстве в нём:
так эндпоинты сохраняют свои внятные ответы («нет окружения»,
«Нет доступа к воркспейсу»), а без указания окружения действуют
app-права, как до Ф8. Создание своего окружения (POST /api/workspaces)
права не требует — лимит проверяет сам эндпоинт.

Сессия (Ф9-fix): весь /api/* без валидной куки получает 401 здесь,
кроме PUBLIC_API_PREFIXES (/api/auth*). Это закрывает и легаси-роуты
(TASKFLOW_LEGACY_UI), которые авторизацию не делают сами.

app-ключи (users, settings) здесь не проверяются: за них отвечают
require_permission / require_role в самих эндпоинтах.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.auth import COOKIE_NAME, verify_session_token
from app.core.permissions import (
    effective_permissions,
    get_workspace_permissions,
    is_feature_available,
    set_request_permissions,
    workspace_id_from_request,
)

# префикс API → обязательный work-ключ
API_PREFIX_PERMISSIONS: tuple[tuple[str, str], ...] = (
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
        return None if method == 'GET' else 'workspace'
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
    if user is None:
        if is_public:
            return await call_next(request)
        return JSONResponse({'detail': 'Not authenticated'}, status_code=401)
    workspace_id = workspace_id_from_request(request)
    permissions = await effective_permissions(user, workspace_id)
    # один набор прав на весь запрос: эндпоинты читают через request_permissions()
    set_request_permissions(user.id, permissions)
    key = required_permission(path, method)
    if key is None:
        return await call_next(request)
    if workspace_id is not None and not permissions.get('all'):
        # явное окружение: право считается по членству в нём (Ф8);
        # не участник — доступ отклонит сам эндпоинт («Нет доступа к воркспейсу»)
        ws_perms = await get_workspace_permissions(user.id, workspace_id)
        if ws_perms is not None and not ws_perms.get(key):
            return JSONResponse({'detail': f'Нет права доступа: {key}'}, status_code=403)
    # без указания окружения work-право проверяет эндпоинт: app-права (legacy)
    # и его внятные сообщения («нет окружения», «Нет доступа к воркспейсу»)
    if not await is_feature_available(user, key, workspace_id):
        return JSONResponse({'detail': f'Функция "{key}" отключена краном доступности'}, status_code=403)
    return await call_next(request)
