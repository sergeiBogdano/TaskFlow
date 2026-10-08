export const SECTION_LABELS: Record<string, string> = {
  '/work': 'Рабочий стол', '/manage': 'Управление пространством', '/admin': 'Администрирование', '/wiki': 'Вики', '/': 'Дашборд', '/tasks': 'Задачи', '/sprints': 'Спринты',
  '/kanban': 'Канбан', '/calendar': 'Календарь', '/notifications': 'Уведомления',
  '/trash': 'Корзина', '/crm': 'CRM', '/clients': 'Клиенты', '/modules': 'Модули',
  '/reports': 'Отчёты', '/ai': 'AI-аналитика', '/notes': 'Заметки',
  '/users': 'Пользователи', '/settings': 'Настройки', '/workspace': 'Окружение',
};

type LabelConfig = {
  nav?: Record<string, { label?: string }>;
  titles?: Record<string, string>;
};

/** One label for the menu, page and editor; old title overrides remain readable. */
export function resolveSectionLabel(config: LabelConfig, route: string, clientsLabel = 'Клиенты'): string {
  return config.nav?.[route]?.label?.trim() || config.titles?.[route]?.trim()
    || (route === '/clients' ? clientsLabel.trim() || 'Клиенты' : SECTION_LABELS[route] || 'TaskFlow');
}

export function resolveFieldLabels(defaults: Record<string, string>, fields?: Record<string, { label?: string }>): Record<string, string> {
  return Object.fromEntries(Object.entries(defaults).map(([key, label]) => [key, fields?.[key]?.label?.trim() || label]));
}
