"""Stable module catalogue. Availability never grants a user's permission."""

MODULES = {
    'tasks': {'label': 'Задачи и планирование', 'keys': ['tasks', 'kanban', 'calendar']},
    'crm': {'label': 'CRM: клиенты и продажи', 'keys': ['crm', 'clients']},
    'notes': {'label': 'Заметки', 'keys': ['notes']},
    'reports': {'label': 'Отчёты', 'keys': ['reports']},
    'automation': {'label': 'Автоматизация', 'keys': ['modules']},
    'ai': {'label': 'ИИ', 'keys': ['ai']},
}

# Explicit versioned defaults: a new entry in MODULES is off in existing spaces.
LEGACY_MODULES = ['tasks', 'crm', 'notes', 'reports', 'automation', 'ai']
PRESET_MODULES = {
    'seo': ['tasks', 'crm', 'notes', 'reports', 'automation'],
    'study': ['tasks', 'notes'],
    'project': ['tasks', 'notes'],
    'empty': ['tasks', 'notes'],
}


def module_for_permission(key: str) -> str | None:
    for name, module in MODULES.items():
        if key in module['keys'] or (name == 'crm' and key.startswith(('crm_', 'client_'))):
            return name
    return None
