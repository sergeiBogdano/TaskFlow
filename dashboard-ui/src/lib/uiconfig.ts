import { getActiveWorkspaceDetail, workspaceClientsLabel, WORKSPACE_EVENT } from './workspace';
import { resolveSectionLabel } from './uiLabels';

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
  tasks?: { order?: string[]; fields?: Record<string, UiFieldOverride> };
  sprints?: { order?: string[]; fields?: Record<string, UiFieldOverride> };
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

export function sectionLabel(route: string): string {
  return resolveSectionLabel(getUiConfig(), route, workspaceClientsLabel());
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

export function taskField(key: string): { label: string; visible: boolean; order: number } {
  const cfg = getUiConfig();
  const item = cfg.tasks?.fields?.[key];
  return {
    order: (cfg.tasks?.order || Object.keys(TASK_FIELD_DEFAULTS)).indexOf(key),
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

export function sprintField(key: string): { label: string; visible: boolean; order: number } {
  const cfg = getUiConfig();
  const item = cfg.sprints?.fields?.[key];
  return {
    order: (cfg.sprints?.order || Object.keys(SPRINT_FIELD_DEFAULTS)).indexOf(key),
    label: item?.label?.trim() || SPRINT_FIELD_DEFAULTS[key] || key,
    visible: item?.visible !== false,
  };
}

export function refreshUiConfig(): void {
  window.dispatchEvent(new CustomEvent(WORKSPACE_EVENT, { detail: { ui: true } }));
}
