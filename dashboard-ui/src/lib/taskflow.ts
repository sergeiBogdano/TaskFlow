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
  todo: { label: 'Создана', short: 'Новая', color: '#a39a8c', soft: 'rgba(163,154,140,.18)', icon: Circle },
  in_progress: { label: 'В работе', short: 'В работе', color: '#2b2620', soft: 'rgba(43,38,32,.1)', icon: Loader2 },
  waiting: { label: 'В ожидании', short: 'Ожидание', color: '#c9c2b4', soft: 'rgba(201,194,180,.25)', icon: PauseCircle },
  client_check: { label: 'На проверке', short: 'Проверка', color: '#6d6355', soft: 'rgba(109,99,85,.14)', icon: Eye },
  done: { label: 'Готово', short: 'Готово', color: '#5f8f6a', soft: 'rgba(95,143,106,.14)', icon: CheckCircle2 },
  overdue: { label: 'Просрочено', short: 'Просрочено', color: '#bc5a48', soft: 'rgba(188,90,72,.13)', icon: AlertTriangle },
} as const;

export const workflowStatuses = ['todo', 'in_progress', 'waiting', 'client_check', 'overdue', 'done'] as const;

export const priorityMeta = {
  low: { label: 'Низкий', color: '#b3aa9c' },
  medium: { label: 'Средний', color: '#6d6355' },
  high: { label: 'Высокий', color: '#2b2620' },
  critical: { label: 'Критический', color: '#bc5a48' },
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
