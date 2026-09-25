import { getActiveWorkspaceDetail, WORKSPACE_EVENT } from './workspace';

export type UiNavOverride = {
  label?: string;
  hint?: string;
  visible?: boolean;
};

export type UiFieldOverride = {
  label?: string;
  visible?: boolean;
};

export type UiConfig = {
  nav?: Record<string, UiNavOverride>;
  titles?: Record<string, string>;
  tasks?: { fields?: Record<string, UiFieldOverride> };
  sprints?: { fields?: Record<string, UiFieldOverride> };
};

export function getUiConfig(): UiConfig {
  const detail = getActiveWorkspaceDetail();
  const raw = detail?.ui_config;
  return raw && typeof raw === 'object' ? (raw as UiConfig) : {};
}

export function navOverride(to: string): UiNavOverride | null {
  const cfg = getUiConfig();
  const item = cfg.nav?.[to];
  return item && typeof item === 'object' ? item : null;
}

export function isNavVisible(to: string): boolean {
  return navOverride(to)?.visible !== false;
}

export function navLabel(to: string, fallback: string): string {
  const label = navOverride(to)?.label?.trim();
  return label || fallback;
}

export function titleOverride(path: string): string | null {
  const cfg = getUiConfig();
  const title = cfg.titles?.[path];
  return typeof title === 'string' && title.trim() ? title.trim() : null;
}

export const TASK_FIELD_DEFAULTS: Record<string, string> = {
  title: 'Название',
  status: 'Статус',
  priority: 'Приоритет',
  taskType: 'Тип',
  client: 'Клиент',
  assignee: 'Исполнитель',
  coExecutors: 'Соисполнители',
  completionDate: 'Дата выполнения',
  deadline: 'Крайний срок',
  visibility: 'Видимость',
  noContract: 'Нет договора',
  notes: 'Описание',
  comment: 'Выполненные работы',
  sprint: 'Спринт',
};

export function taskField(key: string): { label: string; visible: boolean } {
  const cfg = getUiConfig();
  const item = cfg.tasks?.fields?.[key];
  return {
    label: item?.label?.trim() || TASK_FIELD_DEFAULTS[key] || key,
    visible: item?.visible !== false,
  };
}

export const SPRINT_FIELD_DEFAULTS: Record<string, string> = {
  name: 'Название',
  goal: 'Цель спринта',
  start: 'Начало',
  end: 'Конец',
};

export function sprintField(key: string): { label: string; visible: boolean } {
  const cfg = getUiConfig();
  const item = cfg.sprints?.fields?.[key];
  return {
    label: item?.label?.trim() || SPRINT_FIELD_DEFAULTS[key] || key,
    visible: item?.visible !== false,
  };
}

export function refreshUiConfig(): void {
  window.dispatchEvent(new CustomEvent(WORKSPACE_EVENT, { detail: { ui: true } }));
}
