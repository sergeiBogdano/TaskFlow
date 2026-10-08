"""Единый источник прав TaskFlow (каталог функций).

Группы, области (scope app|work), метки и пресеты ролей живут здесь:
- фронт рендерит редактор ролей из GET /api/permissions/catalog;
- database.py сеет роли и идемпотентно дозаполняет новые ключи.
Новые права добавлять только в каталог — дальше на него опираются
каскад-потолок (Ф4), кран доступности (Ф6) и кастомные роли окружения (Ф7).
"""

SCOPE_APP = 'app'
SCOPE_WORK = 'work'
SCOPES = (SCOPE_APP, SCOPE_WORK)

PERMISSION_GROUPS = [
    {
        'id': 'navigation',
        'scope': SCOPE_WORK,
        'title': 'Рабочие разделы окружения',
        'description': 'Что пользователь может видеть и использовать внутри выбранного окружения.',
        'items': [
            {'key': 'dashboard', 'label': 'Дашборд', 'hint': 'Главная сводка и здоровье организаций', 'level': 'basic'},
            {'key': 'tasks', 'label': 'Задачи', 'hint': 'Список задач и создание задач', 'level': 'basic'},
            {'key': 'kanban', 'label': 'Канбан', 'hint': 'Доска статусов и перетаскивание задач', 'level': 'basic'},
            {'key': 'calendar', 'label': 'Календарь', 'hint': 'Задачи по дате выполнения', 'level': 'basic'},
            {'key': 'clients', 'label': 'Клиенты', 'hint': 'Карточки организаций и справочник клиентов', 'level': 'basic'},
            {'key': 'modules', 'label': 'Модули', 'hint': 'Автоматическое создание задач по расписанию', 'level': 'advanced'},
            {'key': 'reports', 'label': 'Отчёты и аналитика', 'hint': 'Отчеты, клиентская аналитика и выгрузки', 'level': 'advanced'},
            {'key': 'notifications', 'label': 'Уведомления', 'hint': 'Личные и системные уведомления', 'level': 'basic'},
            {'key': 'notes', 'label': 'Заметки', 'hint': 'Заметки команды: договорённости и внутренние записи', 'level': 'basic'},
            {'key': 'ai', 'label': 'ИИ и аналитика', 'hint': 'Раздел ИИ: отчёты, аналитика и подсказки нейросети', 'level': 'advanced'},
            {'key': 'workspace', 'label': 'Окружение', 'hint': 'Настройки окружения: участники, вёрстка интерфейса, справочники', 'level': 'advanced'},
        ],
    },
    {
        'id': 'tasks',
        'scope': SCOPE_WORK,
        'title': 'Работа',
        'description': 'Кто какие задачи видит и может выбирать в фильтрах.',
        'items': [
            {'key': 'tasks_view_team', 'label': 'Выбор сотрудника', 'hint': 'Можно смотреть задачи выбранного сотрудника в фильтрах', 'level': 'advanced'},
            {'key': 'tasks_view_others', 'label': 'Видеть чужие задачи', 'hint': 'Доступ к задачам других сотрудников в рамках разрешенных клиентов', 'level': 'sensitive'},
            {'key': 'tasks_view_all', 'label': 'Видеть все задачи', 'hint': 'Максимальный обзор задач команды', 'level': 'sensitive'},
            {'key': 'dashboard_team', 'label': 'Командный дашборд', 'hint': 'Сводки и здоровье организаций по команде, а не только по себе', 'level': 'advanced'},
        ],
    },
    {
        'id': 'clients',
        'scope': SCOPE_WORK,
        'title': 'Клиенты и отчёты',
        'description': 'Доступ к вкладкам клиента. Название организации доступно всем с правом “Клиенты”, а чувствительные вкладки настраиваются отдельно.',
        'items': [
            {'key': 'client_tab_contacts', 'label': 'Контакты', 'hint': 'Контактные лица клиента', 'level': 'basic'},
            {'key': 'client_tab_access', 'label': 'Доступы', 'hint': 'Логины, пароли, URL и доступ пользователей к клиенту', 'level': 'sensitive'},
            {'key': 'client_tab_contracts', 'label': 'Договоры', 'hint': 'Сроки, продления и файлы договоров', 'level': 'sensitive'},
            {'key': 'client_tab_notes', 'label': 'Заметки', 'hint': 'Конкуренты и внутренние заметки клиента', 'level': 'sensitive'},
            {'key': 'client_tab_related', 'label': 'Задачи и модули', 'hint': 'Связанные задачи и подключенные модули клиента', 'level': 'advanced'},
            {'key': 'client_tab_activity', 'label': 'История', 'hint': 'Журнал изменений клиента', 'level': 'advanced'},
            {'key': 'client_edit', 'label': 'Изменение клиентов', 'hint': 'Создание и изменение организаций', 'level': 'advanced'},
            {'key': 'client_delete', 'label': 'Удаление клиентов', 'hint': 'Перемещение клиентов в корзину и массовое удаление', 'level': 'sensitive'},
        ],
    },
    {
        'id': 'system',
        'scope': SCOPE_APP,
        'title': 'Управление приложением',
        'description': 'Глобальные настройки и пользователи. Эти права не зависят от выбранного окружения.',
        'items': [
            {'key': 'users', 'label': 'Пользователи и роли приложения', 'hint': 'Управление аккаунтами и глобальными ролями в доступной области', 'level': 'sensitive'},
            {'key': 'settings', 'label': 'Настройки приложения', 'hint': 'Общие настройки текущего приложения', 'level': 'sensitive'},
            {'key': 'users_password_own', 'label': 'Смена своего пароля', 'hint': 'Пользователь может менять свой собственный пароль'},
        ],
    },
    {
        'id': 'account_security',
        'scope': SCOPE_APP,
        'title': 'Безопасность учётных записей',
        'description': 'Глобальные пароли обслуживают только администраторы учётных записей. Ранг пространства не даёт эти права.',
        'items': [
            {'key': 'users_password_reset', 'label': 'Сброс чужих паролей', 'hint': 'Требует управления учётными записями; сброс паролей обычных аккаунтов. Администраторов и root обслуживает только root.', 'level': 'sensitive'},
        ],
    },
]

PERMISSION_GROUPS.extend([
    {'id': 'platform_access', 'scope': SCOPE_APP, 'title': 'Администрирование', 'description': 'Явные полномочия приложения', 'items': [
        {'key': 'workspaces_create', 'label': 'Создание пространств', 'hint': 'Создавать независимые пространства'},
        {'key': 'users_manage', 'label': 'Управление учётными записями', 'hint': 'Создавать, блокировать и приглашать пользователей'},
    ]},
    {'id': 'crm', 'scope': SCOPE_WORK, 'title': 'CRM', 'description': 'Продажи внутри пространства', 'items': [
        {'key': 'crm', 'label': 'Просмотр CRM', 'hint': 'Воронки, сделки, контакты и активности'},
        {'key': 'crm_edit', 'label': 'Изменение CRM', 'hint': 'Создание и изменение сделок и контактов'},
        {'key': 'crm_delete', 'label': 'Удаление CRM', 'hint': 'Удаление сделок и контактов'},
        {'key': 'crm_configure', 'label': 'Настройка CRM', 'hint': 'Воронки, этапы и поля карточек'},
    ]},
])

PERMISSION_GROUPS.append({'id': 'workspace_management', 'scope': SCOPE_WORK,
    'title': 'Управление окружением', 'description': 'Уровень участника ограничивает, кого можно изменять. Эти разрешения определяют доступные административные действия.', 'items': [
        {'key': 'workspace_settings', 'label': 'Настройки и оформление окружения', 'hint': 'Название, оформление, справочники и общий интерфейс', 'level': 'sensitive'},
        {'key': 'workspace_members', 'label': 'Управление участниками', 'hint': 'Приглашение, исключение и изменение участников ниже своего уровня', 'level': 'sensitive'},
        {'key': 'workspace_profiles', 'label': 'Профили и личные исключения', 'hint': 'Настройка действий и полей для участников ниже своего уровня', 'level': 'sensitive'},
    ]})

PERMISSION_GROUPS.append({'id': 'work_actions', 'scope': SCOPE_WORK, 'title': 'Действия с задачами и спринтами',
    'description': 'Просмотр раздела не равен изменению данных.', 'items': [
        {'key': 'tasks_create', 'label': 'Создавать задачи', 'hint': 'Создание задач', 'level': 'basic'},
        {'key': 'tasks_edit', 'label': 'Изменять доступные задачи', 'hint': 'Поля и статус задач, в которых пользователь участвует', 'level': 'basic'},
        {'key': 'tasks_delete', 'label': 'Удалять и восстанавливать задачи', 'hint': 'Корзина задач', 'level': 'sensitive'},
        {'key': 'sprints_plan', 'label': 'Управлять спринтами', 'hint': 'Создание, изменение сроков и состава спринтов', 'level': 'advanced'},
    ]})

# Freeze defaults: new catalogue keys never expand rank permissions implicitly.
WORKSPACE_ADMIN_DEFAULTS = [
    'dashboard', 'tasks', 'kanban', 'calendar', 'clients', 'notifications', 'notes',
    'tasks_create', 'tasks_edit', 'tasks_delete', 'sprints_plan',
    'workspace_settings', 'workspace_members', 'workspace_profiles',
    'modules', 'reports', 'ai', 'workspace', 'tasks_view_team', 'tasks_view_others',
    'tasks_view_all', 'dashboard_team', 'client_tab_contacts', 'client_tab_access',
    'client_tab_contracts', 'client_tab_notes', 'client_tab_related', 'client_tab_activity', 'client_edit', 'client_delete',
]
WORKSPACE_MEMBER_DEFAULTS = ['tasks_create', 'tasks_edit', 'tasks_delete', 'dashboard', 'tasks', 'kanban', 'calendar', 'clients', 'notifications', 'notes', 'workspace', 'client_tab_contacts']

ROLE_PRESETS = {
    'executor': ['dashboard', 'tasks', 'kanban', 'calendar', 'clients', 'notifications', 'notes', 'workspace', 'users_password_own'],
    'manager': [
        'dashboard', 'dashboard_team', 'tasks', 'tasks_view_team', 'kanban', 'calendar', 'clients',
        'modules', 'reports', 'notifications', 'notes', 'ai', 'workspace',
        'client_tab_contacts', 'client_tab_contracts', 'client_tab_related', 'client_tab_activity', 'client_edit',
        'users_password_own',
    ],
    'admin': [
        'dashboard', 'dashboard_team', 'tasks', 'tasks_view_team', 'tasks_view_others', 'kanban',
        'calendar', 'clients', 'modules', 'reports', 'notifications', 'notes', 'ai', 'workspace',
        'settings', 'users', 'users_manage', 'users_password_reset', 'workspaces_create',
        'client_tab_contacts', 'client_tab_access', 'client_tab_contracts', 'client_tab_notes',
        'client_tab_related', 'client_tab_activity', 'client_edit', 'client_delete',
        'users_password_own',
    ],
}

# Контракт между backend и интерфейсом: глобальные роли приложения не
# смешиваются с ролями участника конкретного окружения.
PLATFORM_ROLE_META = {
    'superadmin': {
        'label': 'Суперадмин (root)',
        'description': 'Первый пользователь платформы. Полный доступ, неизменяемая учётная запись.',
    },
    'admin': {
        'label': 'Администратор приложения',
        'description': 'Глобальные пользователи, роли и настройки в пределах выданных прав.',
    },
    'manager': {
        'label': 'Руководитель команды',
        'description': 'Рабочие процессы, команда и расширенный доступ к задачам.',
    },
    'executor': {
        'label': 'Участник приложения',
        'description': 'Обычная работа в доступных окружениях и свои задачи.',
    },
}

WORKSPACE_ROLE_META = {
    'owner': {
        'label': 'Владелец окружения',
        'description': 'Управляет настройками, составом и удалением этого окружения.',
    },
    'admin': {
        'label': 'Администратор окружения',
        'description': 'Управляет участниками ниже себя, но не владельцем и не общими настройками.',
    },
    'member': {
        'label': 'Участник окружения',
        'description': 'Работает с разрешёнными разделами и не управляет доступом других.',
    },
}

# superadmin не редактируется и не мигрируется: {'all': True}
DEFAULT_ROLE_PERMISSIONS = {
    'superadmin': {'all': True},
    **{name: {key: True for key in keys} for name, keys in ROLE_PRESETS.items()},
}

# Идемпотентное дозаполнение существующих ролей новыми ключами:
# добавляются только отсутствующие ключи (значение True), ничего не удаляется.
# users_password_reset здесь НЕТ осознанно: сброс чужих паролей — opt-in,
# выдаётся явно (роль приложения или кастомная роль окружения).
ROLE_MIGRATION_DEFAULTS = {
    'admin': ['users', 'notes', 'ai', 'workspace', 'users_password_own'],
    'manager': ['notes', 'ai', 'workspace', 'users_password_own'],
    'executor': ['notes', 'workspace', 'users_password_own'],
}


def work_scope_keys() -> list[str]:
    """Ключи только scope=work (конструктор ролей окружения, Ф7)."""
    return [item['key'] for group in PERMISSION_GROUPS if group['scope'] == SCOPE_WORK
            for item in group['items']]


def workspace_default_permissions(rank: str) -> dict:
    """Права по умолчанию в окружении (Ф7).

    owner/admin → полный набор «Работы», member → только базовые
    (без расширений advanced/sensitive).
    users_password_reset исключён из rank-defaults осознанно: иначе любой
    владелец окружения сбрасывал бы пароли добавляемым участникам
    (invite-then-reset) без ведома суперадмина. Право выдаётся явно —
    ролью приложения или кастомной ролью окружения.
    """
    keys = WORKSPACE_ADMIN_DEFAULTS if rank in ('owner', 'admin') else WORKSPACE_MEMBER_DEFAULTS
    return {key: True for key in keys}


def catalog_payload() -> dict:
    """Пayload для GET /api/permissions/catalog."""
    scopes = {
        item['key']: group['scope']
        for group in PERMISSION_GROUPS
        for item in group['items']
    }
    return {
        'groups': PERMISSION_GROUPS,
        'presets': {name: list(keys) for name, keys in ROLE_PRESETS.items()},
        'scopes': scopes,
        'platform_roles': PLATFORM_ROLE_META,
        'workspace_roles': WORKSPACE_ROLE_META,
    }


def _validate() -> None:
    keys = [item['key'] for group in PERMISSION_GROUPS for item in group['items']]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise RuntimeError(f'permission_catalog: дубли ключей: {duplicates}')
    known = set(keys)
    for name, preset in ROLE_PRESETS.items():
        unknown = sorted(set(preset) - known)
        if unknown:
            raise RuntimeError(f'permission_catalog: пресет {name} содержит неизвестные ключи: {unknown}')
    for name, migration_keys in ROLE_MIGRATION_DEFAULTS.items():
        unknown = sorted(set(migration_keys) - known)
        if unknown:
            raise RuntimeError(f'permission_catalog: миграция {name} содержит неизвестные ключи: {unknown}')
        extra = sorted(set(migration_keys) - set(ROLE_PRESETS[name]))
        if extra:
            raise RuntimeError(f'permission_catalog: ключи миграции вне пресета {name}: {extra}')


_validate()
