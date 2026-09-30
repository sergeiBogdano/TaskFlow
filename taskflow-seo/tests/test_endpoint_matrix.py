"""Ф9: полная матрица защиты API endpoint.

Каждый (method, path) попадает ровно в один слой защиты:

  public     — сознательно открытые точки (health, /api/auth*: вход/выход);
  middleware — work-право из карты Ф8 (API_PREFIX_PERMISSIONS) + сессия;
  skip       — префикс вне карты прав (design): только сессия (Ф9-fix);
  guard      — require_permission / require_role / require_workspace_role
               в зависимостях маршрута (маркер _tf_guard);
  allowlist  — осознанно открытый или самопроверяющийся эндпоинт с причиной.

Auth-слой: middleware отдаёт 401 на весь /api/* без валидной сессии,
кроме PUBLIC_API_PREFIXES (Ф9-fix: раньше легаси-роуты TASKFLOW_LEGACY_UI
отдавали анониму 200 на /api/tasks, /api/search, /api/activity и др.).
"""

import pytest
from fastapi.routing import APIRoute

from app.core.permissions import (
    get_current_user,
    require_permission,
    require_role,
    require_workspace_role,
)
from app.web.app import app
from app.web.middleware import (
    PUBLIC_API_PREFIXES,
    _SKIP_PREFIXES,
    required_permission,
)

STRONG_GUARDS = {'permission', 'role', 'ws_role'}

# Осознанные исключения (помимо middleware/skip/guard) с причиной.
# Ключ — (METHOD, path-шаблон как в FastAPI).
ALLOWLIST: dict[tuple[str, str], str] = {
    ('GET', '/api/auth/me'): 'карта прав текущего пользователя для фронта (401 без сессии)',
    ('GET', '/api/permissions/catalog'): 'каталог прав читает любой авторизованный (только чтение)',
    ('GET', '/api/workspaces'): 'список своих окружений бэкенд фильтрует по членству',
    ('GET', '/api/workspaces/presets/list'): 'справочник пресетов создания окружения',
    ('POST', '/api/workspaces'): 'создание своего окружения, лимит 3 проверяется внутри',
    ('GET', '/api/workspaces/{workspace_id}'): 'membership проверяется через resolve_workspace внутри',
    ('GET', '/api/users'): 'справочник для назначений; любой авторизованный (тест: 200)',
    ('POST', '/api/users'): 'права внутри: superadmin либо owner/admin окружения',
    ('PUT', '/api/users/{user_id}/password'): 'смена пароля: свой — можно, чужой — 403 внутри',
    ('POST', '/api/users/change-password'): 'смена своего пароля, текущий пароль проверяется внутри',
    ('GET', '/api/sse'): 'стрим уведомлений: cookie-проверка внутри (плюс 401 от middleware)',
}

# сознательно публичные (без сессии): должны входить в PUBLIC_API_PREFIXES или быть /health
PUBLIC_ROUTES: set[tuple[str, str]] = {
    ('GET', '/health'),
    ('POST', '/api/auth/login'),
    ('POST', '/api/auth/logout'),
    ('GET', '/api/auth/me'),
}


def _iter_api_routes():
    """FastAPI 0.141 лениво оборачивает include_router в _IncludedRouter."""
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, 'original_router'):
            for sub in route.original_router.routes:
                if isinstance(sub, APIRoute):
                    yield sub


def _guard_markers(route: APIRoute) -> set[str]:
    """Рекурсивно собирает маркеры _tf_guard из дерева зависимостей."""
    found: set[str] = set()

    def walk(dep):
        for child in dep.dependencies:
            fn = child.call
            mark = getattr(fn, '_tf_guard', None)
            if mark:
                found.add(mark)
            walk(child)

    walk(route.dependant)
    return found


def _is_public(method: str, path: str) -> bool:
    if not path.startswith('/api/'):
        return True  # health / docs / static
    return path.startswith(PUBLIC_API_PREFIXES)


def _matrix() -> dict[tuple[str, str], tuple[str, str]]:
    """(method, path) -> (слой, деталь)."""
    matrix: dict[tuple[str, str], tuple[str, str]] = {}
    for route in _iter_api_routes():
        for method in sorted(route.methods - {'HEAD', 'OPTIONS'}):
            path = route.path
            key = required_permission(path, method)
            if _is_public(method, path):
                detail = 'health/docs/static' if not path.startswith('/api/') else 'PUBLIC_API_PREFIXES'
                matrix[(method, path)] = ('public', detail)
            elif key is not None:
                matrix[(method, path)] = ('middleware', key)
            elif path.startswith(_SKIP_PREFIXES):
                matrix[(method, path)] = ('skip', 'вне карты work-прав: только сессия (middleware)')
            else:
                markers = _guard_markers(route) & STRONG_GUARDS
                if markers:
                    matrix[(method, path)] = ('guard', '+'.join(sorted(markers)))
                elif (method, path) in ALLOWLIST:
                    matrix[(method, path)] = ('allowlist', ALLOWLIST[(method, path)])
                else:
                    matrix[(method, path)] = ('UNCOVERED', '')
    return matrix


def test_every_endpoint_classified():
    matrix = _matrix()
    uncovered = sorted(k for k, (layer, _) in matrix.items() if layer == 'UNCOVERED')
    assert not uncovered, (
        'Endpoint без слоя защиты (добавь в карту Ф8, guard-dependency '
        'или ALLOWLIST с причиной):\n' + '\n'.join(f'  {m} {p}' for m, p in uncovered)
    )


def test_matrix_is_substantial():
    matrix = _matrix()
    # все маршруты реально собраны (FastAPI/инвентарь не сломан)
    assert len(matrix) >= 130
    layers = {layer for layer, _ in matrix.values()}
    assert {'middleware', 'public'} <= layers
    assert layers <= {'middleware', 'skip', 'guard', 'allowlist', 'public'}


def test_public_routes_are_exactly_auth_and_health():
    """Сознательно публичные — только health и /api/auth*; всё остальное
    /api/* обязано проходить сессию (middleware 401)."""
    for (method, path), (layer, _) in _matrix().items():
        if layer != 'public' or not path.startswith('/api/'):
            continue
        assert path.startswith(PUBLIC_API_PREFIXES), (
            f'{method} {path}: публичен, но вне PUBLIC_API_PREFIXES'
        )
    # и наоборот: из PUBLIC_API_PREFIXES не должен исчезнуть auth
    assert any(path.startswith('/api/auth') for path in PUBLIC_API_PREFIXES)


def test_middleware_keys_are_work_scope():
    from app.core.permission_catalog import work_scope_keys

    keys = set(work_scope_keys()) | {'workspace'}
    for (method, path), (layer, detail) in _matrix().items():
        if layer == 'middleware':
            assert detail in keys, f'{method} {path}: неизвестное work-право {detail!r}'


def test_allowlist_no_stale_entries():
    matrix = _matrix()
    present = set(matrix)
    stale = sorted(set(ALLOWLIST) - present)
    assert not stale, 'Протухшие записи ALLOWLIST (маршрута больше нет): ' + repr(stale)


def test_skip_prefixes_only_need_session():
    """Skip-префиксы вне карты прав: прав не требуется, но сессия обязательна —
    на это полагается middleware-401 (Ф9-fix)."""
    for route in _iter_api_routes():
        for method in sorted(route.methods - {'HEAD', 'OPTIONS'}):
            path = route.path
            if not path.startswith(_SKIP_PREFIXES):
                continue
            if _is_public(method, path):
                continue  # /api/auth
            assert required_permission(path, method) is None, (
                f'{method} {path}: skip-префикс вдруг получил work-ключ'
            )


@pytest.mark.parametrize('url', [
    '/api/search?q=test',
    '/api/activity',
    '/api/files/1/download',
    '/api/tasks',
    '/api/clients',
    '/api/notifications',
])
def test_anonymous_api_gets_401(sync_request, url):
    """Auth-слой middleware (Ф9-fix): без сессии любой /api/* — 401,
    даже легаси-роуты, которые авторизацию не делают."""
    resp = sync_request('GET', url)
    assert resp.status_code == 401, f'{url} -> {resp.status_code} (ожидали 401)'


def test_public_auth_endpoints_work_without_session(sync_request):
    assert sync_request('POST', '/api/auth/login',
                        json={'username': 'x', 'password': 'y'}).status_code in (401, 400)
    assert sync_request('GET', '/api/auth/me').status_code == 401


def test_guard_factories_marked():
    """Маркеры _tf_guard читаются из фабричных check-функций."""
    assert getattr(require_role(['x']), '_tf_guard') == 'role'
    assert getattr(require_permission('tasks'), '_tf_guard') == 'permission'
    assert getattr(require_workspace_role('admin'), '_tf_guard') == 'ws_role'
    assert getattr(get_current_user, '_tf_guard') == 'auth'
