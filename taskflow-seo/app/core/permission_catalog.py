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
        'title': 'Разделы приложения',
        'description': 'Какие основные разделы будут видны пользователю в меню.',
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
            {'key': 'client_delete', 'label': 'Удаление клиентов', 'hint': 'Перемещение клиентов в корзину и массовое удаление', 'level': 'sensitive'},
        ],
    },
    {
        'id': 'system',
        'scope': SCOPE_APP,
        'title': 'Система',
        'description': 'Администрирование приложения. Эти права лучше выдавать редко.',
        'items': [
            {'key': 'users', 'label': 'Пользователи и роли', 'hint': 'Создание пользователей, назначение ролей, настройка прав', 'level': 'sensitive'},
            {'key': 'settings', 'label': 'Настройки', 'hint': 'Системные настройки приложения', 'level': 'sensitive'},
        ],
    },
]

ROLE_PRESETS = {
    'executor': ['dashboard', 'tasks', 'kanban', 'calendar', 'clients', 'notifications', 'notes', 'workspace'],
    'manager': [
        'dashboard', 'dashboard_team', 'tasks', 'tasks_view_team', 'kanban', 'calendar', 'clients',
        'modules', 'reports', 'notifications', 'notes', 'ai', 'workspace',
        'client_tab_contacts', 'client_tab_contracts', 'client_tab_related', 'client_tab_activity',
    ],
    'admin': [
        'dashboard', 'dashboard_team', 'tasks', 'tasks_view_team', 'tasks_view_others', 'kanban',
        'calendar', 'clients', 'modules', 'reports', 'notifications', 'notes', 'ai', 'workspace',
        'settings', 'users',
        'client_tab_contacts', 'client_tab_access', 'client_tab_contracts', 'client_tab_notes',
        'client_tab_related', 'client_tab_activity', 'client_delete',
    ],
}

# superadmin не редактируется и не мигрируется: {'all': True}
DEFAULT_ROLE_PERMISSIONS = {
    'superadmin': {'all': True},
    **{name: {key: True for key in keys} for name, keys in ROLE_PRESETS.items()},
}

# Идемпотентное дозаполнение существующих ролей новыми ключами:
# добавляются только отсутствующие ключи (значение True), ничего не удаляется.
ROLE_MIGRATION_DEFAULTS = {
    'admin': ['users', 'notes', 'ai', 'workspace'],
    'manager': ['notes', 'ai', 'workspace'],
    'executor': ['notes', 'workspace'],
}


def work_scope_keys() -> list[str]:
    """Ключи только scope=work (конструктор ролей окружения, Ф7)."""
    return [item['key'] for group in PERMISSION_GROUPS if group['scope'] == SCOPE_WORK
            for item in group['items']]


def workspace_default_permissions(rank: str) -> dict:
    """Права по умолчанию в окружении (Ф7).

    owner/admin → полный набор «Работы»; member → только базовые
    (без расширений advanced/sensitive).
    """
    keys = work_scope_keys()
    if rank in ('owner', 'admin'):
        return {key: True for key in keys}
    basic = {item['key'] for group in PERMISSION_GROUPS if group['scope'] == SCOPE_WORK
             for item in group['items'] if item.get('level') == 'basic'}
    return {key: True for key in keys if key in basic}


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
