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
  todo: { label: 'Создана', short: 'Новая', color: '#60a5fa', soft: 'rgba(96,165,250,.14)', icon: Circle },
  in_progress: { label: 'В работе', short: 'В работе', color: '#facc15', soft: 'rgba(250,204,21,.14)', icon: Loader2 },
  waiting: { label: 'В ожидании', short: 'Ожидание', color: '#d1d5db', soft: 'rgba(209,213,219,.12)', icon: PauseCircle },
  client_check: { label: 'На проверке', short: 'Проверка', color: '#fb923c', soft: 'rgba(251,146,60,.14)', icon: Eye },
  done: { label: 'Готово', short: 'Готово', color: '#4ade80', soft: 'rgba(74,222,128,.14)', icon: CheckCircle2 },
  overdue: { label: 'Просрочено', short: 'Просрочено', color: '#f87171', soft: 'rgba(248,113,113,.14)', icon: AlertTriangle },
} as const;

export const workflowStatuses = ['todo', 'in_progress', 'waiting', 'client_check', 'overdue', 'done'] as const;

export const priorityMeta = {
  low: { label: 'Низкий', color: '#94a3b8' },
  medium: { label: 'Средний', color: '#facc15' },
  high: { label: 'Высокий', color: '#fb923c' },
  critical: { label: 'Критический', color: '#f87171' },
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
