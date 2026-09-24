import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Eye,
  Loader2,
  PauseCircle,
  ShieldCheck,
  UserRoundCheck,
} from 'lucide-react';

export const statusMeta = {
  todo: { label: 'Создана', short: 'Новая', color: 'var(--color-st-todo)', soft: 'var(--color-st-todo-soft)', icon: Circle },
  in_progress: { label: 'В работе', short: 'В работе', color: 'var(--color-st-progress)', soft: 'var(--color-st-progress-soft)', icon: Loader2 },
  waiting: { label: 'В ожидании', short: 'Ожидание', color: 'var(--color-st-wait)', soft: 'var(--color-st-wait-soft)', icon: PauseCircle },
  client_check: { label: 'На проверке', short: 'Проверка', color: 'var(--color-st-check)', soft: 'var(--color-st-check-soft)', icon: Eye },
  done: { label: 'Готово', short: 'Готово', color: 'var(--color-st-done)', soft: 'var(--color-st-done-soft)', icon: CheckCircle2 },
  overdue: { label: 'Просрочено', short: 'Просрочено', color: 'var(--color-st-overdue)', soft: 'var(--color-st-overdue-soft)', icon: AlertTriangle },
} as const;

export const workflowStatuses = ['todo', 'in_progress', 'waiting', 'client_check', 'overdue', 'done'] as const;

export const priorityMeta = {
  low: { label: 'Низкий', color: 'var(--color-pr-low)' },
  medium: { label: 'Средний', color: 'var(--color-pr-medium)' },
  high: { label: 'Высокий', color: 'var(--color-pr-high)' },
  critical: { label: 'Критический', color: 'var(--color-pr-critical)' },
} as const;

export const taskTypeMeta: Record<string, string> = {
  article: 'Статья',
  description: 'Описание',
  product_card: 'Карточка',
  design: 'Дизайн',
  seo: 'SEO',
  dev: 'Разработка',
  custom: 'Другое',
};

export const roleMeta: Record<string, { label: string; hint: string; icon: typeof ShieldCheck }> = {
  superadmin: { label: 'Суперадмин', hint: 'Полный доступ и роли', icon: ShieldCheck },
  admin: { label: 'Администратор', hint: 'Пользователи, настройки, модули', icon: ShieldCheck },
  manager: { label: 'Руководитель', hint: 'Команда, сроки, все задачи', icon: UserRoundCheck },
  executor: { label: 'Исполнитель', hint: 'Свои и публичные задачи', icon: UserRoundCheck },
};

export function formatDate(value?: string | null) {
  if (!value) return 'Без срока';
  const dateOnly = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) {
    return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3])).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' });
  }
  return new Date(value).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' });
}

export function formatFullDate(value?: string | null) {
  if (!value) return 'Не задано';
  const dateOnly = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) {
    return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3])).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
  }
  return new Date(value).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
}

export function daysUntil(value?: string | null) {
  if (!value) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const date = new Date(value);
  date.setHours(0, 0, 0, 0);
  return Math.ceil((date.getTime() - today.getTime()) / 86400000);
}

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}
