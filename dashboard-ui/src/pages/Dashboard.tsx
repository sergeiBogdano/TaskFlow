import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock3,
  ListTodo,
  UserRound,
  UsersRound,
} from 'lucide-react';
import { api } from '../api/client';
import { SearchSelect } from '../components/SearchSelect';
import type { DashboardStats, OrganizationOverview, OrganizationOverviewItem, Task } from '../api/client';
import { daysUntil, formatDate, statusMeta } from '../lib/taskflow';

type OrganizationFilter = 'all' | 'attention' | 'stale' | 'unassigned';

export function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [overview, setOverview] = useState<OrganizationOverview | null>(null);
  const [expiring, setExpiring] = useState<any[]>([]);
  const [tasks, setTasks] = useState<Partial<Task>[]>([]);
  const [scope, setScope] = useState<'mine' | 'all'>('mine');
  const [selectedUserId, setSelectedUserId] = useState('');
  const [organizationFilter, setOrganizationFilter] = useState<OrganizationFilter>('all');
  const [loading, setLoading] = useState(true);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.getDashboardStats(), api.getExpiring(), api.getDashboardFocus(7)])
      .then(([dashboardStats, expiringClients, taskList]) => {
        setStats(dashboardStats);
        setExpiring(expiringClients);
        setTasks(taskList);
      })
      .catch(() => navigate('/login'))
      .finally(() => setLoading(false));
  }, [navigate]);

  useEffect(() => {
    setOverviewLoading(true);
    setError('');
    api.getOrganizationOverview(selectedUserId ? 'mine' : scope, selectedUserId ? Number(selectedUserId) : undefined)
      .then(setOverview)
      .catch(err => setError(err instanceof Error ? err.message : 'Не удалось загрузить организации.'))
      .finally(() => setOverviewLoading(false));
  }, [scope, selectedUserId]);

  const focusTasks = tasks;

  const organizations = useMemo(() => (overview?.items || []).filter(item => {
    if (organizationFilter === 'attention') return item.needs_attention;
    if (organizationFilter === 'stale') return item.is_stale;
    if (organizationFilter === 'unassigned') return item.responsible_users.length === 0;
    return true;
  }), [organizationFilter, overview]);

  if (loading || !stats) {
    return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка рабочего пространства...</div>;
  }

  const cards = [
    { label: 'Видимых задач', value: stats.total, icon: ListTodo, color: 'var(--color-accent)', to: '/tasks' },
    { label: 'В работе', value: stats.in_progress, icon: Clock3, color: 'var(--color-warning)', to: '/kanban' },
    { label: 'Просрочено', value: stats.overdue, icon: AlertTriangle, color: 'var(--color-danger)', to: '/tasks?status=overdue' },
    { label: 'Готово', value: stats.done, icon: CheckCircle2, color: 'var(--color-success)', to: '/reports' },
  ];

  return (
    <div className="mx-auto max-w-[1500px] space-y-5">
      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {cards.map(card => (
          <button key={card.label} onClick={() => navigate(card.to)} className="tf-panel-flat p-4 text-left hover:border-[var(--color-border-strong)]">
            <div className="mb-3 flex items-center justify-between">
              <div className="grid h-9 w-9 place-items-center rounded-lg" style={{ background: `${card.color}22`, color: card.color }}><card.icon size={18} /></div>
              <ArrowRight size={15} className="text-[var(--color-muted)]" />
            </div>
            <div className="text-3xl font-black" style={{ color: card.color }}>{card.value}</div>
            <div className="mt-1 text-sm text-[var(--color-text-secondary)]">{card.label}</div>
          </button>
        ))}
      </section>

      <section className="tf-panel-flat overflow-hidden">
        <div className="border-b border-[var(--color-border)] p-4 lg:p-5">
          <div className="flex flex-wrap items-start gap-3">
            <div>
              <div className="flex items-center gap-2"><Building2 size={18} className="text-[var(--color-accent)]" /><h2 className="text-base font-bold">{scope === 'mine' && !selectedUserId ? 'Мои организации' : 'Организации команды'}</h2></div>
              <p className="mt-1 text-sm text-[var(--color-text-secondary)]">Где идёт работа, что требует внимания и с кем давно не было активности.</p>
            </div>
            {overview?.can_view_team && (
              <div className="ml-auto flex flex-wrap gap-2">
                <button type="button" onClick={() => { setScope('mine'); setSelectedUserId(''); }} className={scope === 'mine' && !selectedUserId ? 'tf-button tf-button-primary' : 'tf-button'}><UserRound size={15} />Мои</button>
                <button type="button" onClick={() => { setScope('all'); setSelectedUserId(''); }} className={scope === 'all' && !selectedUserId ? 'tf-button tf-button-primary' : 'tf-button'}><UsersRound size={15} />Вся команда</button>
                <div className="min-w-52">
                  <SearchSelect
                    value={selectedUserId}
                    options={overview.users.map(user => ({ value: String(user.id), label: user.username }))}
                    onChange={value => { setSelectedUserId(value); if (value) setScope('all'); }}
                    emptyLabel="Выбрать сотрудника"
                    searchPlaceholder="Найти сотрудника"
                  />
                </div>
              </div>
            )}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {([
              ['all', 'Все'],
              ['attention', 'Требуют внимания'],
              ['stale', 'Без активности 14 дней'],
              ['unassigned', 'Без ответственного'],
            ] as [OrganizationFilter, string][]).map(([key, label]) => (
              <button key={key} type="button" onClick={() => setOrganizationFilter(key)} className={organizationFilter === key ? 'tf-button tf-button-primary' : 'tf-button'}>{label}</button>
            ))}
          </div>
        </div>

        {error && <div className="border-b border-[var(--color-border)] px-5 py-3 text-sm text-[var(--color-danger)]">{error}</div>}
        {overviewLoading ? (
          <div className="p-8 text-center text-sm text-[var(--color-text-secondary)]">Обновляем сводку...</div>
        ) : (
          <div className="divide-y divide-[var(--color-border)]/70">
            {organizations.map(item => <OrganizationRow key={item.id} item={item} onOpenClient={() => navigate(`/clients/${item.id}`)} onOpenTasks={() => navigate(`/tasks?client_id=${item.id}`)} />)}
            {organizations.length === 0 && <div className="p-8 text-center text-sm text-[var(--color-text-secondary)]">В этом представлении организаций пока нет.</div>}
          </div>
        )}
      </section>

      <section className="grid grid-cols-1 gap-5 xl:grid-cols-[1.15fr_.85fr]">
        <div className="tf-panel-flat overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] p-4">
            <div><h2 className="text-sm font-bold">Фокус на сегодня</h2><p className="text-xs text-[var(--color-text-secondary)]">Ближайшие сроки и просрочки</p></div>
            <button onClick={() => navigate('/tasks')} className="text-xs font-semibold text-[var(--color-accent)]">Все задачи</button>
          </div>
          <div className="divide-y divide-[var(--color-border)]/70">
            {focusTasks.map(task => {
              const meta = statusMeta[task.status as keyof typeof statusMeta] || statusMeta.todo;
              const due = daysUntil(task.completion_date || task.deadline);
              return (
                <button key={task.id} onClick={() => navigate(`/tasks?task=${task.id}`)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-[var(--color-surface-2)]">
                  <span className="h-3 w-1.5 shrink-0 rounded-full" style={{ background: meta.color }} />
                  <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{task.title}</div><div className="mt-1 truncate text-xs text-[var(--color-text-secondary)]">{task.client || 'Без клиента'} · {formatDate(task.completion_date || task.deadline)}</div></div>
                  <span className="text-xs font-semibold" style={{ color: due !== null && due < 0 ? 'var(--color-danger)' : 'var(--color-text-secondary)' }}>{due === null ? 'без срока' : due < 0 ? `${Math.abs(due)} дн. проср.` : due === 0 ? 'сегодня' : `${due} дн.`}</span>
                </button>
              );
            })}
            {focusTasks.length === 0 && <div className="p-6 text-center text-sm text-[var(--color-text-secondary)]">Нет срочных задач.</div>}
          </div>
        </div>

        <div className="tf-panel-flat overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] p-4">
            <div><h2 className="text-sm font-bold">Договоры на исходе</h2><p className="text-xs text-[var(--color-text-secondary)]">Проверить продление или завершение работ</p></div>
            <CalendarClock size={17} className="text-[var(--color-warning)]" />
          </div>
          <div className="divide-y divide-[var(--color-border)]/70">
            {expiring.map(client => (
              <button key={client.id} onClick={() => navigate(`/clients/${client.id}`)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-[var(--color-surface-2)]">
                <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{client.org_name}</div><div className="text-xs text-[var(--color-text-secondary)]">Окончание: {formatDate(client.contract_end)}</div></div>
                <ArrowRight size={14} className="text-[var(--color-muted)]" />
              </button>
            ))}
            {expiring.length === 0 && <div className="p-6 text-sm text-[var(--color-text-secondary)]">Нет договоров на исходе.</div>}
          </div>
        </div>
      </section>
    </div>
  );
}

function OrganizationRow({ item, onOpenClient, onOpenTasks }: { item: OrganizationOverviewItem; onOpenClient: () => void; onOpenTasks: () => void }) {
  return (
    <div className="grid gap-3 px-4 py-4 hover:bg-[var(--color-surface-2)]/55 lg:grid-cols-[minmax(220px,1.25fr)_repeat(4,82px)_minmax(220px,1fr)_auto] lg:items-center">
      <button type="button" onClick={onOpenClient} className="min-w-0 text-left">
        <div className="flex items-center gap-2"><span className="truncate text-sm font-bold">{item.name}</span>{item.needs_attention && <AlertTriangle size={14} className="shrink-0 text-[var(--color-warning)]" />}</div>
        <div className="mt-1 truncate text-xs text-[var(--color-text-secondary)]">{item.domain || 'Без домена'} · {item.responsible_users.join(', ') || 'Без ответственного'}</div>
      </button>
      <Metric label="Активно" value={item.active} />
      <Metric label="Просрочено" value={item.overdue} tone={item.overdue ? 'danger' : undefined} />
      <Metric label="На неделе" value={item.due_soon} tone={item.due_soon ? 'warning' : undefined} />
      <Metric label="Готово" value={item.done_this_month} tone="success" />
      <div className="min-w-0 text-xs">
        <div className="truncate font-semibold">{item.nearest_task?.title || 'Нет ближайшей задачи'}</div>
        <div className={item.is_stale ? 'mt-1 text-[var(--color-warning)]' : 'mt-1 text-[var(--color-text-secondary)]'}>{activityLabel(item)}</div>
      </div>
      <div className="flex gap-2 lg:justify-end"><button type="button" onClick={onOpenTasks} className="tf-button">Задачи</button><button type="button" onClick={onOpenClient} className="tf-button w-9 px-0" title="Открыть организацию"><ArrowRight size={15} /></button></div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: 'danger' | 'warning' | 'success' }) {
  const color = tone === 'danger' ? 'var(--color-danger)' : tone === 'warning' ? 'var(--color-warning)' : tone === 'success' ? 'var(--color-success)' : 'var(--color-text-primary)';
  return <div><div className="text-base font-black" style={{ color }}>{value}</div><div className="text-[11px] text-[var(--color-muted)]">{label}</div></div>;
}

function activityLabel(item: OrganizationOverviewItem) {
  if (item.inactive_days === null) return 'Активности ещё не было';
  if (item.inactive_days === 0) return 'Активность сегодня';
  return `Без активности ${item.inactive_days} дн.`;
}
