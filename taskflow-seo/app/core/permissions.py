from fastapi import Depends, HTTPException, Request

from contextvars import ContextVar

# effective-права текущего запроса: middleware (Ф8) кладёт их один раз,
# эндпоинты читают через request_permissions() — один и тот же набор на запрос
_REQUEST_PERMISSIONS: ContextVar[tuple[int, dict] | None] = ContextVar(
    'request_permissions', default=None
)


def set_request_permissions(user_id: int, permissions: dict) -> None:
    _REQUEST_PERMISSIONS.set((user_id, dict(permissions)))



async def get_current_user(request: Request):
    from app.core.auth import COOKIE_NAME, session_matches_user, verify_session_token
    from app.services.user_service import get_user
    token = request.cookies.get(COOKIE_NAME, '')
    uid = verify_session_token(token)
    user = await get_user(uid) if uid is not None else None
    if not session_matches_user(token, user):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# маркер для матрицы защиты endpoint (Ф9): tests/test_endpoint_matrix.py
# отличает по маркеру require_permission / require_role / require_workspace_role
get_current_user._tf_guard = 'auth'


async def get_user_role_names(user_id: int) -> set[str]:
    from sqlalchemy import select
    from app.core.database import async_session
    from app.core.models import Role, UserRole

    async with async_session() as session:
        result = await session.execute(select(UserRole).where(UserRole.user_id == user_id))
        names: set[str] = set()
        for user_role in result.scalars().all():
            role = await session.get(Role, user_role.role_id)
            if role and not role.deleted_at:
                names.add(role.name)
        from app.core.models import User
        account = await session.get(User, user_id)
        names.discard('superadmin')
        if account and account.is_root:
            names.add('superadmin')
        return names


async def get_user_permissions(user_id: int) -> dict:
    import json
    from sqlalchemy import select
    from app.core.database import async_session
    from app.core.models import Group, Role, UserGroup, UserRole

    async with async_session() as session:
        result = await session.execute(select(UserRole).where(UserRole.user_id == user_id))
        permissions: dict = {}
        for user_role in result.scalars().all():
            role = await session.get(Role, user_role.role_id)
            if not role or role.deleted_at:
                continue
            role_permissions = json.loads(role.permissions or '{}') if isinstance(role.permissions, str) else (role.permissions or {})
            for k, v in role_permissions.items():
                permissions[k] = bool(v) or permissions.get(k, False)
        # группы — additive: только добавляют к правам ролей
        group_rows = (await session.execute(
            select(UserGroup).where(UserGroup.user_id == user_id)
        )).scalars().all()
        for link in group_rows:
            group = await session.get(Group, link.group_id)
            if not group or group.deleted_at:
                continue
            group_permissions = (
                json.loads(group.permissions or '{}')
                if isinstance(group.permissions, str) else (group.permissions or {})
            )
            permissions.update({k: True for k, v in group_permissions.items() if v})
        from app.core.models import User
        account = await session.get(User, user_id)
        if account and account.is_root:
            return {'all': True}
        permissions.pop('all', None)
        permissions.setdefault('users_password_own', True)
        return permissions


async def get_workspace_permissions(user_id: int, workspace_id: int | None) -> dict | None:
    """Work-права участника окружения (Ф7/Ф8 + точный набор роли).

    Нет кастомной роли → фиксированная база ранга; новые права
    по умолчанию выключены. Есть кастомная роль → ТОЧНО её набор, база ранга
    не добавляется: что отмечено в роли, то и действует. Ранг при этом
    сохраняется и продолжает gating административных действий
    (участники, удаление). Пароли управляются на уровне приложения.
    Пустая кастомная роль запрещена на уровне API, но на всякий случай
    трактуется как отсутствие прав, а не как база ранга.

    None — пользователь не участник окружения (или окружение не задано).
    """
    if not workspace_id:
        return None
    import json

    from sqlalchemy import select

    from app.core.database import async_session
    from app.core.models import WorkspaceMember, WorkspaceRole
    from app.core.permission_catalog import work_scope_keys, workspace_default_permissions

    async with async_session() as session:
        member = (await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )).scalar_one_or_none()
        if member is None:
            return None
        from app.core.access_policy import parse_policy
        role = await session.get(WorkspaceRole, member.custom_role_id) if member.custom_role_id else None
        if member.custom_role_id and (not role or role.deleted_at or role.workspace_id != workspace_id):
            return {}
        allowed = set(work_scope_keys())
        raw = parse_policy(role.permissions) if role and role.workspace_id == workspace_id else workspace_default_permissions(member.role)
        result = {key: True for key, value in raw.items() if value and key in allowed}
        overrides = parse_policy(member.access_overrides).get('permissions', {})
        result.update({key: value for key, value in overrides.items() if key in allowed and isinstance(value, bool)})
        return result


async def effective_permissions(user, workspace_id: int | None = None) -> dict:
    """Effective-набор прав пользователя (Ф8).

    - app-ключи (scope=app) — как раньше, из ролей и групп;
    - work-ключи (scope=work) — из активного окружения: точный набор
      кастомной роли, если назначена, иначе фиксированная база ранга. Если окружения нет или
      пользователь не участник — остаются только глобальные app-права;
    - только фактический root (`all`) — полный доступ.
    """
    from app.core.permission_catalog import work_scope_keys

    app_perms = await get_user_permissions(user.id)
    if is_root_user(user):
        return {'all': True}
    if app_perms.get('all'):
        return app_perms
    ws_perms = await get_workspace_permissions(user.id, workspace_id)
    work_keys = set(work_scope_keys())
    merged = {key: value for key, value in app_perms.items() if key not in work_keys}
    merged.update(ws_perms or {})
    return merged


async def request_permissions(user, workspace_id: int | None = None) -> dict:
    """Права текущего запроса: из контекста middleware (Ф8), иначе пересчёт.

    Возвращает копию — можно безопасно мутировать.
    """
    cached = _REQUEST_PERMISSIONS.get()
    permissions = dict(cached[1]) if cached is not None and cached[0] == user.id else await effective_permissions(user, workspace_id)
    if permissions.get('all'):
        return permissions
    state = await get_effective_features(user, workspace_id, keys=list(permissions))
    return {key: bool(value) and state.get(key, False) for key, value in permissions.items()}


async def user_can_manage_all_tasks(user) -> bool:
    roles = await get_user_role_names(user.id)
    return 'superadmin' in roles


def user_is_superadmin(role_names: set[str]) -> bool:
    return 'superadmin' in role_names


def is_root_user(user) -> bool:
    """Return the immutable platform-root marker without a database query."""
    return bool(getattr(user, 'is_root', False))


async def get_accessible_client_ids(session, user_id: int, role_names: set[str]) -> set[int]:
    if user_is_superadmin(role_names):
        return set()

    from sqlalchemy import select
    from app.core.models import UserClientAccess

    result = await session.execute(
        select(UserClientAccess.client_id).where(UserClientAccess.user_id == user_id)
    )
    return {row[0] for row in result.all() if row[0] is not None}


def client_is_visible_to_user(client_id: int | None, role_names: set[str], accessible_client_ids: set[int]) -> bool:
    """Organizations are a shared directory; sensitive tabs are permission-gated separately."""
    return True


def user_can_view_client_tab(role_names: set[str], permissions: dict, tab: str) -> bool:
    if user_is_superadmin(role_names) or permissions.get('all'):
        return True
    if tab == 'main':
        return True
    return bool(permissions.get(f'client_tab_{tab}'))


def user_can_access_task_client(task, role_names: set[str], accessible_client_ids: set[int]) -> bool:
    return client_is_visible_to_user(getattr(task, 'client_id', None), role_names, accessible_client_ids)


def task_co_executor_ids(task) -> set[int]:
    ids = {getattr(task, 'co_executor_id', None)}
    ids.update(getattr(link, 'user_id', None) for link in getattr(task, 'co_executor_links', []) or [])
    return {user_id for user_id in ids if user_id is not None}


def task_is_visible_to_user(task, user, role_names: set[str], accessible_client_ids: set[int] | None = None, permissions: dict | None = None) -> bool:
    permissions = permissions or {}
    if user_is_superadmin(role_names) or permissions.get('all') or permissions.get('tasks_view_all') or permissions.get('tasks_view_others'):
        return True
    if accessible_client_ids is not None and not user_can_access_task_client(task, role_names, accessible_client_ids):
        return False
    return user.id in {task.creator_id, task.assignee_id} | task_co_executor_ids(task)


def task_is_editable_by_user(task, user, role_names: set[str], accessible_client_ids: set[int] | None = None, permissions: dict | None = None) -> bool:
    permissions = permissions or {}
    if user_is_superadmin(role_names):
        return True
    if accessible_client_ids is not None and not user_can_access_task_client(task, role_names, accessible_client_ids):
        return False
    return user.id in {task.creator_id, task.assignee_id} | task_co_executor_ids(task)


def require_role(roles: list[str]):
    async def check(user=Depends(get_current_user)):
        names = await get_user_role_names(user.id)
        if names.intersection(roles):
            return user
        raise HTTPException(status_code=403, detail="Forbidden")
    check._tf_guard = 'role'
    return check


def require_root():
    """Dependency for operations reserved for the first platform account."""
    async def check(user=Depends(get_current_user)):
        if not is_root_user(user):
            raise HTTPException(status_code=403, detail='Только root-пользователь может выполнить эту операцию')
        return user
    # Keep endpoint protection visible to the existing protection matrix.
    check._tf_guard = 'role'
    return check


def require_permission(key: str):
    """Доступ по праву из каталога + кран доступности функции (Ф6).

    Суперадмин с `all` проходит проверку прав, но кран действует на всех:
    выключенная функция → 403 даже для суперадмина (кроме самого крана
    и ключа `settings` — он не может быть выключен).
    """
    async def check(request: Request, user=Depends(get_current_user)):
        permissions = await request_permissions(user, workspace_id_from_request(request))
        if not (permissions.get('all') or permissions.get(key)):
            raise HTTPException(status_code=403, detail=f'Нет права "{key}"')
        if not await is_feature_available(user, key, workspace_id_from_request(request)):
            raise HTTPException(status_code=403, detail=f'Функция "{key}" отключена краном доступности')
        return user
    check._tf_guard = 'permission'
    return check


def workspace_id_from_request(request: Request | None) -> int | None:
    """workspace_id активного окружения: путь /api/workspaces/{id}/…, иначе query.

    Фронт подставляет query на всех /api/* кроме auth; управление окружением
    идёт по пути — id ресурса в пути важнее query.
    """
    if request is None:
        return None
    if hasattr(request.state, 'workspace_id'):
        return request.state.workspace_id
    path = request.url.path
    prefix = '/api/workspaces/'
    if path.startswith(prefix):
        segment = path[len(prefix):].split('/', 1)[0]
        if segment.isdigit():
            return int(segment)
    raw = request.query_params.get('workspace_id')
    if raw and str(raw).isdigit():
        return int(raw)
    return None


def require_any_permission(*keys: str):
    """An account manager can read the role directory without role-edit privileges."""
    async def check(request: Request, user=Depends(get_current_user)):
        workspace_id = workspace_id_from_request(request)
        permissions = await request_permissions(user, workspace_id)
        for key in keys:
            if (permissions.get('all') or permissions.get(key)) and await is_feature_available(user, key, workspace_id):
                return user
        raise HTTPException(status_code=403, detail='Нет права доступа к управлению пользователями')
    check._tf_guard = 'permission'
    return check


def _catalog_feature_keys() -> set[str]:
    from app.core.permission_catalog import PERMISSION_GROUPS
    return {item['key'] for group in PERMISSION_GROUPS for item in group['items']}


async def get_global_feature_state(keys: list[str] | None = None) -> dict[str, bool]:
    """Состояние крана только на глобальном уровне (для выдачи прав в ролях)."""
    from sqlalchemy import select
    from app.core.database import async_session
    from app.core.models import FeatureOverride

    if keys is None:
        keys = sorted(_catalog_feature_keys())
    async with async_session() as session:
        rows = (await session.execute(
            select(FeatureOverride).where(
                FeatureOverride.scope == 'global',
                FeatureOverride.key.in_(keys or ['']),
            )
        )).scalars().all()
    from app.core.workspace_modules import module_for_permission
    from app.core.permission_catalog import WORKSPACE_ADMIN_DEFAULTS
    legacy_keys = set(WORKSPACE_ADMIN_DEFAULTS) | {'settings', 'users', 'users_password_own', 'users_password_reset', 'users_manage', 'workspaces_create', 'crm', 'crm_edit', 'crm_delete', 'crm_configure'}
    state = {key: key in legacy_keys for key in keys}
    for row in rows:
        state[row.key] = bool(row.enabled)
    return state


async def get_effective_features(user, workspace_id: int | None = None,
                                 keys: list[str] | None = None, reasons: dict | None = None) -> dict[str, bool]:
    """Эффективная доступность функций: приоритет user > workspace > group > global.

    Новый ключ без явного разрешения выключен; выключенная функция
    приостанавливается (выдачи в ролях не трогаются).
    """
    from sqlalchemy import or_, select
    from app.core.database import async_session
    from app.core.models import FeatureOverride, Group, UserGroup

    if keys is None:
        keys = sorted(_catalog_feature_keys())
    if not keys:
        return {}
    async with async_session() as session:
        user_groups = (await session.execute(
            select(Group).join(UserGroup, Group.id == UserGroup.group_id).where(UserGroup.user_id == user.id, Group.deleted_at.is_(None))
        )).scalars().all()
        group_ids = [group.id for group in user_groups]
        group_names = {group.id: group.name for group in user_groups}
        conds = [FeatureOverride.scope == 'global']
        if workspace_id is not None:
            conds.append((FeatureOverride.scope == 'workspace') & (FeatureOverride.target_id == workspace_id))
        if group_ids:
            conds.append((FeatureOverride.scope == 'group') & (FeatureOverride.target_id.in_(group_ids)))
        conds.append((FeatureOverride.scope == 'user') & (FeatureOverride.target_id == user.id))
        rows = (await session.execute(
            select(FeatureOverride).where(or_(*conds), FeatureOverride.key.in_(keys))
        )).scalars().all()
    from app.core.workspace_modules import module_for_permission
    from app.core.permission_catalog import WORKSPACE_ADMIN_DEFAULTS
    legacy_keys = set(WORKSPACE_ADMIN_DEFAULTS) | {'settings', 'users', 'users_password_own', 'users_password_reset', 'users_manage', 'workspaces_create', 'crm', 'crm_edit', 'crm_delete', 'crm_configure'}
    state = {key: is_root_user(user) or key in legacy_keys for key in keys}
    reasons = reasons if reasons is not None else {}
    reasons.update({key: '' if state[key] else 'Новая функция не включена явно' for key in keys})
    scope_labels = {'global': 'Функция выключена для приложения', 'group': 'Функция запрещена в группе пользователя', 'workspace': 'Функция выключена в настройках пространства', 'user': 'Функция выключена лично для пользователя'}
    # At the same group priority, denial wins regardless of database row order.
    for scope in ('global', 'group', 'workspace', 'user'):
        for key in keys:
            matching = [row for row in rows if row.scope == scope and row.key == key]
            values = [bool(row.enabled) for row in matching]
            if values and not is_root_user(user):
                state[key] = all(values)
                reasons[key] = '' if state[key] else scope_labels[scope]
                if not state[key] and scope == 'group':
                    reasons[key] += ': ' + ', '.join(sorted({group_names[row.target_id] for row in matching if not row.enabled}))
    # Global disable and space module disable are hard limits; user overrides cannot reopen them.
    for row in rows:
        if not is_root_user(user) and row.scope in ('global', 'workspace') and not row.enabled and row.key in state:
            state[row.key] = False
            reasons[row.key] = scope_labels[row.scope]
    if workspace_id is not None:
        import json
        from app.core.models import Workspace
        async with async_session() as session:
            space = await session.get(Workspace, workspace_id)
        enabled_modules = json.loads(space.enabled_modules or '[]') if space else []
        for key in keys:
            module = module_for_permission(key)
            if module and module not in enabled_modules:
                state[key] = False
                reasons[key] = 'Модуль выключен в пространстве'
    if workspace_id and not is_root_user(user):
        from app.core.access_policy import field_access
        fields = await field_access(user, workspace_id)
        if any(mode == 'hidden' for values in fields.values() for mode in values.values()):
            for derived in ('dashboard', 'reports', 'modules'):
                if derived in state:
                    state[derived] = False
                    reasons[derived] = 'Скрытые поля ограничивают этот раздел'
        if any(fields['tasks'].get(key) == 'hidden' for key in ('deadline', 'completionDate', 'assignee', 'client')) and 'calendar' in state:
            state['calendar'] = False
            reasons['calendar'] = 'Для календаря скрыты необходимые поля задач'
    return state


async def get_feature_access(user, workspace_id=None):
    reasons = {}
    state = await get_effective_features(user, workspace_id, reasons=reasons)
    return {key: {'available': enabled, 'reason': reasons.get(key, '')} for key, enabled in state.items()}


async def is_feature_available(user, key: str, workspace_id: int | None = None) -> bool:
    if is_root_user(user):
        from app.core.workspace_modules import module_for_permission
        if workspace_id is not None and module_for_permission(key):
            import json
            from app.core.models import Workspace
            from app.core.database import async_session
            async with async_session() as session:
                space = await session.get(Workspace, workspace_id)
            return bool(space and module_for_permission(key) in json.loads(space.enabled_modules or '[]'))
        return True
    state = await get_effective_features(user, workspace_id, keys=[key])
    return state.get(key, True)


async def assert_features_grantable(permissions: dict):
    """Выдать право можно только если функция включена краном (глобально)."""
    if not permissions:
        return
    catalog_keys = _catalog_feature_keys()
    keys = sorted(k for k, v in permissions.items() if v and k in catalog_keys)
    if not keys:
        return
    state = await get_global_feature_state(keys)
    blocked = sorted(k for k in keys if not state.get(k, True))
    if blocked:
        raise HTTPException(
            status_code=403,
            detail='Функции отключены краном доступности: ' + ', '.join(blocked),
        )


def assert_within_ceiling(granter_permissions: dict, target_permissions: dict,
                          detail: str = 'Нельзя выдать права выше своих'):
    """Единый потолок (правило 3): записываемые права ⊆ прав вызывающего.

    Суперадмин (`all`) проходит без проверки. Ложные значения (`False`)
    потолок не нарушают — это снятие права, а не выдача.
    """
    if granter_permissions.get('all'):
        return
    extra = sorted(
        key for key, value in (target_permissions or {}).items()
        if value and not granter_permissions.get(key)
    )
    if extra:
        raise HTTPException(status_code=403, detail=f'{detail}: {", ".join(extra)}')


async def get_workspace_role(session, user_id: int, workspace_id: int) -> str | None:
    from sqlalchemy import select
    from app.core.models import WorkspaceMember
    row = (await session.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )).scalar_one_or_none()
    return row.role if row else None


async def resolve_workspace(session, user, role_names: set[str], workspace_id: int | None, allow_deleted: bool = False):
    """Возвращает воркспейс + роль пользователя в нём.

    workspace_id=None означает окружение пользователя по умолчанию:
    первое доступное пользователю (для суперадмина — первое в системе).
    Суперадмин имеет доступ везде.
    Удалённые окружения по умолчанию не резолвятся (404).
    """
    from sqlalchemy import select
    from app.core.models import Workspace, WorkspaceMember
    if workspace_id is None:
        if user_is_superadmin(role_names):
            workspace = (await session.execute(
                select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.id)
            )).scalars().first()
            if workspace is None:
                raise HTTPException(status_code=404, detail="Воркспейс не найден")
        else:
            # Первое окружение, членом которого является пользователь.
            # Раньше здесь бралось первое окружение в БД, из-за чего
            # участники не-первого окружения получали 403 «Нет доступа».
            workspace = (await session.execute(
                select(Workspace)
                .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                .where(
                    WorkspaceMember.user_id == user.id,
                    Workspace.deleted_at.is_(None),
                )
                .order_by(Workspace.id)
            )).scalars().first()
            if workspace is None:
                raise HTTPException(
                    status_code=403,
                    detail="У вас нет пространства. Попросите администратора пригласить вас.",
                )
    else:
        workspace = await session.get(Workspace, workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Воркспейс не найден")
    if workspace.deleted_at is not None and not allow_deleted:
        raise HTTPException(status_code=404, detail="Воркспейс не найден")
    if user_is_superadmin(role_names):
        return workspace, "owner"
    role = await get_workspace_role(session, user.id, workspace.id)
    if role is None:
        raise HTTPException(status_code=403, detail="Нет доступа к воркспейсу")
    return workspace, role


def workspace_role_rank(role: str | None) -> int:
    return {"owner": 3, "admin": 2, "member": 1}.get(role or "", 0)


def require_workspace_role(*allowed: str):
    """Проверка роли внутри воркспейса.

    workspace_id берётся из пути (id ресурса важнее), иначе из query —
    как в workspace_id_from_request. Query НЕ должен затенять путь:
    иначе запрос к /api/workspaces/{B}/... с ?workspace_id={A}
    молча применяется к окружению A.
    """
    async def check(request: Request, user=Depends(get_current_user)):
        from sqlalchemy import select
        from app.core.database import async_session
        from app.core.models import Workspace
        raw = request.path_params.get("workspace_id") or request.query_params.get("workspace_id")
        workspace_id = int(raw) if raw and str(raw).isdigit() else None
        async with async_session() as session:
            role_names = await get_user_role_names(user.id)
            workspace, role = await resolve_workspace(session, user, role_names, workspace_id)
            if role not in allowed and not user_is_superadmin(role_names):
                raise HTTPException(status_code=403, detail="Недостаточно прав в воркспейсе")
            return {"user": user, "workspace": workspace, "role": role, "role_names": role_names}
    check._tf_guard = 'ws_role'
    return check


def require_workspace_management(key):
    async def check(request: Request, user=Depends(get_current_user)):
        ctx = await require_workspace_role('owner', 'admin')(request, user)
        permissions = await request_permissions(user, ctx['workspace'].id)
        if not user.is_root and not (permissions.get(key) and await is_feature_available(user, key, ctx['workspace'].id)):
            raise HTTPException(403, 'Нет разрешения: ' + key)
        return ctx
    check._tf_guard = 'ws_role'
    return check
