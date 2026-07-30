import { lazy, Suspense, useEffect, useMemo, useState, type ChangeEvent, type ClipboardEvent, type FormEvent, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Activity, AlertTriangle, BarChart3, CalendarDays, CalendarRange, CheckCircle2, ExternalLink, KeyRound, ListFilter, NotebookText, Paperclip, Plus, RefreshCw, Save, Search, Target, Trash2, Upload, UserRoundCheck, X } from 'lucide-react';
import { api } from '../api/client';
import type { Client, ClientAnalytics, ClientFile, ClientWorkSummary, OrganizationHealth, Task, User } from '../api/client';
import { referenceCache } from '../api/cache';
import { TaskScopeFilter, type TaskScope } from '../components/TaskScopeFilter';
import { useAuth } from '../hooks/useAuth';
import { formatDate, statusMeta, taskTypeMeta } from '../lib/taskflow';

const TaskModal = lazy(() => import('./Tasks').then(module => ({ default: module.TaskModal })));

type ContactDraft = { id?: number; fio: string; position: string; phone: string; email: string };
type ContractDraft = { id?: number; contract_type: string; start_date: string; end_date: string; status: string };
type AccessDraft = { id?: number; title: string; url: string; login: string; password: string; note?: string };

const emptyContact: ContactDraft = { fio: '', position: '', phone: '', email: '' };
const emptyContract: ContractDraft = { contract_type: '', start_date: '', end_date: '', status: 'active' };
const contractTypeOptions = [
  'SEO-продвижение',
  'Комплексное SEO',
  'Техническое сопровождение',
  'Контент и статьи',
  'SEO-аудит',
  'Разработка сайта',
  'Поддержка сайта',
  'Реклама и аналитика',
  'Разовая работа',
];
const emptyAccess: AccessDraft = { title: '', url: '', login: '', password: '', note: '' };

export function Clients() {
  const { user: currentUser, hasRole } = useAuth();
  const { id } = useParams();
  const navigate = useNavigate();
  const [clients, setClients] = useState<Client[]>([]);
  const [summaries, setSummaries] = useState<Record<number, ClientWorkSummary>>({});
  const [selectedTasks, setSelectedTasks] = useState<Task[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [filter, setFilter] = useState('');
  const [view, setView] = useState<'all' | 'mine' | 'attention' | 'stale' | 'unassigned'>('all');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [contractFilter, setContractFilter] = useState<'all' | 'active' | 'expired' | 'none'>('all');
  const [contractSort, setContractSort] = useState<'none' | 'asc' | 'desc'>('none');
  const [loading, setLoading] = useState(true);
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [activity, setActivity] = useState<any[]>([]);
  const [section, setSection] = useState<'list' | 'analytics'>('list');
  const canAnalytics = hasRole('superadmin') || Boolean(currentUser?.permissions?.all || currentUser?.permissions?.reports);

  const load = async () => {
    const [clientList, summaryList, userList] = await Promise.all([
      referenceCache.clients(),
      api.getClientWorkSummaries().catch(() => []),
      referenceCache.users().catch(() => []),
    ]);
    setClients(clientList);
    setSummaries(Object.fromEntries(summaryList.map(item => [item.client_id, item])));
    setUsers(userList);
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!id) return;
    Promise.all([api.getClient(Number(id)), api.getTasks(`client_id=${Number(id)}`).catch(() => [])]).then(([client, clientTasks]) => {
      setSelectedClient(client);
      setSelectedTasks(clientTasks);
      setShowModal(true);
    }).catch(() => undefined);
  }, [id]);

  const filtered = useMemo(() => clients.filter(client => {
    const matchesSearch = client.org_name.toLowerCase().includes(filter.toLowerCase()) || (client.domain || '').toLowerCase().includes(filter.toLowerCase());
    if (!matchesSearch) return false;
    const summary = summaries[client.id];
    const overdue = Boolean(summary?.overdue);
    const latestActivity = summary?.last_activity ? new Date(summary.last_activity).getTime() : 0;
    const stale = !latestActivity || Date.now() - latestActivity >= 14 * 24 * 60 * 60 * 1000;
    const mineByTask = Boolean(summary?.total);
    const mine = Boolean(currentUser && (client.responsible_user_ids || []).includes(currentUser.id)) || mineByTask;
    const contractEnd = client.contract_end ? new Date(client.contract_end).getTime() : 0;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    if (contractFilter === 'active' && (!contractEnd || contractEnd < today.getTime())) return false;
    if (contractFilter === 'expired' && (!contractEnd || contractEnd >= today.getTime())) return false;
    if (contractFilter === 'none' && contractEnd) return false;
    if (view === 'mine') return mine;
    if (view === 'attention') return overdue || stale || !(client.responsible_user_ids || []).length;
    if (view === 'stale') return stale;
    if (view === 'unassigned') return !(client.responsible_user_ids || []).length;
    return true;
  }).sort((left, right) => {
    if (contractSort === 'none') return left.org_name.localeCompare(right.org_name, 'ru');
    if (!left.contract_end && !right.contract_end) return left.org_name.localeCompare(right.org_name, 'ru');
    if (!left.contract_end) return 1;
    if (!right.contract_end) return -1;
    const leftEnd = new Date(left.contract_end).getTime();
    const rightEnd = new Date(right.contract_end).getTime();
    const difference = leftEnd - rightEnd;
    return (contractSort === 'asc' ? difference : -difference) || left.org_name.localeCompare(right.org_name, 'ru');
  }), [clients, contractFilter, contractSort, currentUser, filter, summaries, view]);

  const activeFilterCount = Number(view !== 'all') + Number(contractFilter !== 'all') + Number(contractSort !== 'none');

  const openClient = async (client: Client) => {
    const [fresh, clientTasks] = await Promise.all([
      api.getClient(client.id).catch(() => client),
      api.getTasks(`client_id=${client.id}`).catch(() => []),
    ]);
    setSelectedClient(fresh);
    setSelectedTasks(clientTasks);
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setSelectedClient(null);
    setSelectedTasks([]);
    setActivity([]);
    if (id) navigate('/clients');
  };

  const loadActivity = async (clientId: number) => {
    setActivity(await api.getClientActivity(clientId));
  };

  const saveClient = async () => {
    closeModal();
    referenceCache.invalidate(['clients']);
    await load();
  };

  const toggleSelected = (clientId: number) => {
    setSelectedIds(prev => prev.includes(clientId) ? prev.filter(id => id !== clientId) : [...prev, clientId]);
  };

  const bulkDelete = async () => {
    if (!selectedIds.length) return;
    if (!confirm(`Удалить выбранные организации в корзину: ${selectedIds.length}?`)) return;
    await api.bulkClients(selectedIds, 'delete');
    setSelectedIds([]);
    referenceCache.invalidate(['clients']);
    await load();
  };

  const deleteClient = async (clientId: number) => {
    if (!confirm('Удалить организацию в корзину? Ее можно будет восстановить.')) return;
    await api.deleteClient(clientId);
    closeModal();
    referenceCache.invalidate(['clients']);
    await load();
  };

  if (loading) return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка клиентов...</div>;

  return (
    <div className="mx-auto max-w-[1500px] space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-xl font-black">Клиенты</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">Карточки с договором, контактами, доступами, задачами и автоматизациями.</p>
        </div>
        <button onClick={() => { setSelectedClient(null); setShowModal(true); }} className="tf-button tf-button-primary ml-auto"><Plus size={16} />Новый клиент</button>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-[var(--color-border)] pb-3">
        <button type="button" onClick={() => setSection('list')} className={section === 'list' ? 'tf-button tf-button-primary' : 'tf-button'}><UserRoundCheck size={15} />Организации</button>
        {canAnalytics && <button type="button" onClick={() => setSection('analytics')} className={section === 'analytics' ? 'tf-button tf-button-primary' : 'tf-button'}><BarChart3 size={15} />Аналитика</button>}
      </div>

      {section === 'analytics' && canAnalytics && <ClientAnalyticsPanel clients={clients} users={users} />}

      {section === 'list' && <section className="tf-panel-flat p-3">
        <div className="flex flex-wrap items-center gap-2">
          <input className="tf-input max-w-xl" placeholder="Поиск по клиенту или домену" value={filter} onChange={event => setFilter(event.target.value)} />
          <button type="button" onClick={() => setFiltersOpen(previous => !previous)} className={filtersOpen || activeFilterCount ? 'tf-button tf-button-primary' : 'tf-button'}><ListFilter size={15} />Фильтры{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ''}</button>
          <div className="ml-auto text-sm text-[var(--color-text-secondary)]">Выбрано: {selectedIds.length}</div>
          <button onClick={bulkDelete} disabled={!selectedIds.length} className="tf-button text-[var(--color-danger)]"><Trash2 size={15} />В корзину</button>
        </div>
        {filtersOpen && <div className="mt-3 grid gap-3 border-t border-[var(--color-border)] pt-3 xl:grid-cols-[1fr_220px_230px_auto]">
          <div className="flex flex-wrap gap-2">
            {[
              ['all', 'Все'],
              ['mine', 'Мои'],
              ['attention', 'Требуют внимания'],
              ['stale', 'Без активности'],
              ['unassigned', 'Без ответственного'],
            ].map(([key, label]) => <button key={key} type="button" onClick={() => setView(key as typeof view)} className={view === key ? 'tf-button tf-button-primary' : 'tf-button'}>{label}</button>)}
          </div>
          <select className="tf-input" value={contractFilter} onChange={event => setContractFilter(event.target.value as typeof contractFilter)}>
            <option value="all">Любой договор</option>
            <option value="active">Договор действует</option>
            <option value="expired">Договор закончился</option>
            <option value="none">Срок не указан</option>
          </select>
          <select className="tf-input" value={contractSort} onChange={event => setContractSort(event.target.value as typeof contractSort)}>
            <option value="none">По названию</option>
            <option value="asc">Сначала ближайшее окончание</option>
            <option value="desc">Сначала позднее окончание</option>
          </select>
          <button type="button" className="tf-button" onClick={() => { setView('all'); setContractFilter('all'); setContractSort('none'); }}>Сбросить</button>
        </div>}
      </section>}

      {section === 'list' && <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {filtered.map(client => {
          const summary = summaries[client.id];
          const total = summary?.total || 0;
          const active = summary?.active || 0;
          const overdue = summary?.overdue || 0;
          return (
            <button key={client.id} onClick={() => openClient(client)} className="tf-panel-flat block w-full p-4 text-left hover:border-[var(--color-border-strong)]">
              <div className="mb-3 flex min-w-0 items-start gap-3">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(client.id)}
                  onClick={event => event.stopPropagation()}
                  onChange={() => toggleSelected(client.id)}
                  className="mt-2 shrink-0 accent-[var(--color-accent)]"
                  aria-label={`Выбрать ${client.org_name}`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-2">
                    <FaviconBadge client={client} />
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-base font-bold leading-tight">{client.org_name}</h3>
                      <p className="truncate text-sm text-[var(--color-text-secondary)]">{client.domain || 'Без домена'}</p>
                    </div>
                  </div>
                  {client.client_warning && <span className="mt-2 inline-flex items-center gap-1 rounded-full border border-[var(--color-warning)]/50 bg-[var(--color-warning)]/15 px-2 py-0.5 text-[11px] font-bold text-[var(--color-warning)]"><AlertTriangle size={12} />Важно для задач</span>}
                </div>
                {client.domain && <a href={normalizeUrl(client.domain)} target="_blank" onClick={event => event.stopPropagation()} className="mt-1 shrink-0 text-[var(--color-muted)] hover:text-[var(--color-accent)]"><ExternalLink size={16} /></a>}
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <InfoChip label="Задач" value={total} />
                <InfoChip label="Активных" value={active} tone="warning" />
                <InfoChip label="Просроч." value={overdue} tone="danger" />
              </div>
              <div className="mt-3 flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
                <CalendarDays size={13} />
                <span>Договор до {formatDate(client.contract_end)}</span>
              </div>
              <div className="mt-2 flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
                <UserRoundCheck size={13} />
                <span className="truncate">{(client.responsible_user_ids || []).map(id => users.find(user => user.id === id)?.username).filter(Boolean).join(', ') || 'Ответственный не назначен'}</span>
              </div>
            </button>
          );
        })}
        {filtered.length === 0 && <div className="tf-panel-flat p-8 text-center text-sm text-[var(--color-text-secondary)]">Клиентов по этому запросу нет.</div>}
      </section>}

      {showModal && (
        <ClientModal
          client={selectedClient}
          tasks={selectedTasks}
          users={users}
          activity={activity}
          onLoadActivity={loadActivity}
          onClose={closeModal}
          onSave={saveClient}
          onDelete={selectedClient ? () => deleteClient(selectedClient.id) : undefined}
          permissions={currentUser?.permissions || {}}
          isSuperadmin={hasRole('superadmin')}
        />
      )}
    </div>
  );
}

function isoDate(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function monthBounds(offset: number) {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth() + offset, 1);
  const end = new Date(today.getFullYear(), today.getMonth() + offset + 1, 0);
  return { start: isoDate(start), end: isoDate(end) };
}

function ClientAnalyticsPanel({ clients, users }: { clients: Client[]; users: User[] }) {
  const current = monthBounds(0);
  const [selectedIds, setSelectedIds] = useState<number[]>(() => clients.map(client => client.id));
  const [periodStart, setPeriodStart] = useState(current.start);
  const [periodEnd, setPeriodEnd] = useState(current.end);
  const [scope, setScope] = useState<TaskScope>('mine');
  const [scopeUserId, setScopeUserId] = useState('');
  const [data, setData] = useState<ClientAnalytics | null>(null);
  const [openedTask, setOpenedTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [organizationSearch, setOrganizationSearch] = useState('');
  const [expanded, setExpanded] = useState<{ clientId: number; group: 'completed' | 'other' } | null>(null);
  const visibleClients = useMemo(() => {
    const query = organizationSearch.trim().toLocaleLowerCase('ru-RU');
    if (!query) return clients;
    return clients.filter(client => `${client.org_name} ${client.domain || ''}`.toLocaleLowerCase('ru-RU').includes(query));
  }, [clients, organizationSearch]);

  useEffect(() => {
    setSelectedIds(prev => prev.filter(id => clients.some(client => client.id === id)));
  }, [clients]);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setData(await api.getClientAnalytics({
        client_ids: selectedIds,
        period_start: periodStart,
        period_end: periodEnd,
        scope,
        scope_user_id: scopeUserId,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить аналитику.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const maxType = Math.max(1, ...(data?.by_type.map(item => item.count) || [1]));
  const modules = data?.modules || [];

  const openTask = async (taskId: number) => {
    try {
      setOpenedTask(await api.getTask(taskId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось открыть задачу.');
    }
  };

  const saveOpenedTask = async (payload: Partial<Task>) => {
    if (!openedTask) return;
    await api.updateTask(openedTask.id, payload);
    setOpenedTask(null);
    await load();
  };

  const deleteOpenedTask = async () => {
    if (!openedTask) return;
    if (!confirm('Переместить задачу в корзину?')) return;
    await api.deleteTask(openedTask.id);
    setOpenedTask(null);
    await load();
  };

  return (
    <div className="space-y-4">
      <section className="tf-panel-flat p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 className="flex items-center gap-2 text-xl font-black"><CalendarRange size={20} />Аналитика по организациям</h3>
            <p className="mt-1 max-w-2xl text-sm leading-5 text-[var(--color-text-secondary)]">Один период, выбранные организации, готовые задачи отдельно от всех остальных статусов.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={filtersOpen ? 'tf-button tf-button-primary' : 'tf-button'} onClick={() => setFiltersOpen(prev => !prev)}><ListFilter size={15} />Фильтры</button>
            <button type="button" className="tf-button tf-button-primary" onClick={load} disabled={loading}><RefreshCw size={15} className={loading ? 'animate-spin' : ''} />{loading ? 'Считаю...' : 'Построить'}</button>
          </div>
        </div>

        {filtersOpen && <div className="mt-5 grid gap-4 border-t border-[var(--color-border)] pt-4 xl:grid-cols-[360px_minmax(320px,480px)_1fr]">
          <PeriodFields title="Период" hint="Можно выбрать месяц, неделю или один день" start={periodStart} end={periodEnd} onStart={setPeriodStart} onEnd={setPeriodEnd} />
          <div>
            <div className="mb-2 text-sm font-bold">Чьи задачи учитывать</div>
            <div className="mb-2 text-xs text-[var(--color-muted)]">Так же, как в задачах, календаре и канбане.</div>
            <TaskScopeFilter
              users={users}
              scope={scope}
              userId={scopeUserId}
              onScopeChange={value => { setScope(value); if (value !== 'user') setScopeUserId(''); }}
              onUserChange={setScopeUserId}
            />
          </div>
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div><div className="text-sm font-bold">Организации</div><div className="text-xs text-[var(--color-muted)]">Выбрано: {selectedIds.length} из {clients.length}</div></div>
              <div className="flex gap-2"><button type="button" className="tf-button px-2.5 py-1.5 text-xs" onClick={() => setSelectedIds(clients.map(client => client.id))}>Выбрать все</button><button type="button" className="tf-button px-2.5 py-1.5 text-xs" onClick={() => setSelectedIds([])}>Снять все</button></div>
            </div>
            <label className="relative mb-2 block"><Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" /><input className="tf-input tf-input-icon" value={organizationSearch} onChange={event => setOrganizationSearch(event.target.value)} placeholder="Найти организацию или домен" /></label>
            <div className="grid max-h-96 grid-cols-1 gap-1 overflow-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 md:grid-cols-2 xl:grid-cols-3">
              {visibleClients.map(client => <label key={client.id} className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-[var(--color-surface-3)]"><input type="checkbox" checked={selectedIds.includes(client.id)} onChange={() => setSelectedIds(prev => prev.includes(client.id) ? prev.filter(id => id !== client.id) : [...prev, client.id])} /><span className="min-w-0"><span className="block truncate font-semibold">{client.org_name}</span>{client.domain && <span className="block truncate text-xs text-[var(--color-muted)]">{client.domain}</span>}</span></label>)}
            </div>
          </div>
        </div>}
        {error && <div className="mt-4 rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">{error}</div>}
      </section>

      {data && <>
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Metric label="Организаций" value={data.summary.organizations} icon={<UserRoundCheck size={16} />} />
          <Metric label="Всего задач" value={data.summary.total} icon={<CalendarDays size={16} />} />
          <Metric label="Готово" value={data.summary.completed} icon={<CheckCircle2 size={16} />} />
          <Metric label="В работе" value={data.summary.other} icon={<Activity size={16} />} tone="warning" />
          <Metric label="Просрочено" value={data.summary.overdue} icon={<AlertTriangle size={16} />} tone="danger" />
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.05fr_.95fr]">
          <div className="tf-panel-flat p-4 sm:p-5">
            <h3 className="text-base font-black">Типы выполненных работ</h3>
            <div className="mt-5 space-y-4">
              {data.by_type.map(item => <div key={item.type}><div className="mb-1 flex items-center justify-between gap-3 text-sm"><span className="font-semibold">{taskTypeMeta[item.type] || item.type}</span><span className="whitespace-nowrap font-black">{item.count}</span></div><div className="h-2 rounded-full bg-[var(--color-surface-3)]"><div className="h-2 rounded-full bg-[var(--color-accent)]" style={{ width: `${Math.max(item.count ? 3 : 0, item.count / maxType * 100)}%` }} /></div></div>)}
              {!data.by_type.length && <div className="rounded-lg border border-dashed border-[var(--color-border-strong)] px-4 py-8 text-center text-sm text-[var(--color-text-secondary)]">Готовых задач за период нет.</div>}
            </div>
          </div>
          <div className="tf-panel-flat p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-base font-black">Модули по организациям</h3>
              <span className="tf-chip text-[var(--color-warning)]">Без модулей: {data.summary.without_modules || 0}</span>
            </div>
            <div className="mt-4 max-h-72 space-y-2 overflow-auto">
              {modules.map(item => (
                <div key={item.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0"><div className="truncate text-sm font-bold">{item.name}</div><div className="truncate text-xs text-[var(--color-muted)]">{item.domain || 'Без домена'}</div></div>
                    <span className={item.module_count ? 'tf-chip text-[var(--color-accent)]' : 'tf-chip text-[var(--color-warning)]'}>{item.module_count}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.modules.map(module => <span key={module} className="tf-chip">{module}</span>)}
                    {!item.modules.length && <span className="text-xs text-[var(--color-muted)]">Модули не подключены.</span>}
                  </div>
                </div>
              ))}
              {!modules.length && <div className="rounded-lg border border-dashed border-[var(--color-border-strong)] px-4 py-8 text-center text-sm text-[var(--color-text-secondary)]">Нет данных по модулям.</div>}
            </div>
          </div>
        </section>

        <section className="space-y-2">
          {data.by_client.map(item => {
            const opened = expanded?.clientId === item.id;
            const tasks = expanded?.group === 'completed' ? item.completed_tasks : item.other_tasks;
            return <article key={item.id} className="tf-panel-flat p-4">
              <div className="flex flex-wrap items-center gap-3">
                <div className="min-w-0 flex-1"><div className="truncate font-bold">{item.name}</div><div className="truncate text-xs text-[var(--color-muted)]">{item.domain || 'Без домена'}</div></div>
                <span className="tf-chip text-[var(--color-accent)]">Готово: {item.completed}</span>
                <span className="tf-chip text-[var(--color-warning)]">В работе: {item.other}</span>
                <span className="tf-chip text-[var(--color-danger)]">Просрочено: {item.overdue}</span>
                <button type="button" className="tf-button" onClick={() => setExpanded(opened && expanded?.group === 'completed' ? null : { clientId: item.id, group: 'completed' })}>Готовые задачи</button>
                <button type="button" className="tf-button" onClick={() => setExpanded(opened && expanded?.group === 'other' ? null : { clientId: item.id, group: 'other' })}>Остальные задачи</button>
              </div>
              {opened && <div className="mt-3 divide-y divide-[var(--color-border)] rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]">
                {tasks.map(task => <button key={task.id} type="button" onClick={() => openTask(task.id)} className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-[var(--color-surface-3)]"><span className="w-14 shrink-0 text-xs text-[var(--color-muted)]">#{task.id}</span><span className="min-w-0 flex-1 truncate font-semibold">{task.title}</span><span className="hidden text-xs text-[var(--color-muted)] md:inline">{taskTypeMeta[task.task_type] || task.task_type}</span><span className="text-xs" style={{ color: statusMeta[task.status as keyof typeof statusMeta]?.color }}>{statusMeta[task.status as keyof typeof statusMeta]?.label || task.status}</span></button>)}
                {!tasks.length && <div className="px-3 py-6 text-center text-sm text-[var(--color-text-secondary)]">Задач в этой группе нет.</div>}
              </div>}
            </article>;
          })}
          {!data.by_client.length && <div className="tf-panel-flat p-8 text-center text-sm text-[var(--color-text-secondary)]">За период нет организаций с задачами.</div>}
        </section>
      </>}
      {openedTask && (
        <Suspense fallback={null}>
          <TaskModal task={openedTask} clients={clients} users={users} onClose={() => setOpenedTask(null)} onSave={saveOpenedTask} onDelete={deleteOpenedTask} onAfterChange={load} />
        </Suspense>
      )}
    </div>
  );
}

function PeriodFields({ title, hint, start, end, onStart, onEnd }: { title: string; hint: string; start: string; end: string; onStart: (value: string) => void; onEnd: (value: string) => void }) {
  return <div><div className="mb-2 text-sm font-bold">{title}</div><div className="mb-2 text-xs text-[var(--color-muted)]">{hint}</div><div className="grid grid-cols-2 gap-2"><label className="text-xs text-[var(--color-text-secondary)]">С <input className="tf-input mt-1" type="date" value={start} onChange={event => onStart(event.target.value)} /></label><label className="text-xs text-[var(--color-text-secondary)]">По <input className="tf-input mt-1" type="date" value={end} onChange={event => onEnd(event.target.value)} /></label></div></div>;
}

function Metric({ label, value, icon, tone = 'accent' }: { label: string; value: number; icon: ReactNode; tone?: 'accent' | 'warning' | 'danger' }) {
  const color = tone === 'warning' ? 'var(--color-warning)' : tone === 'danger' ? 'var(--color-danger)' : 'var(--color-accent)';
  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4"><div className="flex items-center gap-2 text-xs font-semibold text-[var(--color-text-secondary)]" style={{ color }}>{icon}{label}</div><div className="mt-2 text-3xl font-black" style={{ color }}>{value}</div></div>;
}

function FaviconBadge({ client }: { client: Client | null }) {
  const initials = client?.org_name?.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'OR';
  const fallbackUrl = client?.domain ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(client.domain)}&sz=64` : '';
  const source = client?.favicon_url || fallbackUrl;
  return <span className="relative grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-accent)]/15 text-[11px] font-black text-[var(--color-accent)]">
    {initials}
    {source && <img src={source} alt="" className="absolute inset-0 h-full w-full bg-[var(--color-surface-2)] object-contain p-1" onError={event => { if (fallbackUrl && event.currentTarget.src !== fallbackUrl) event.currentTarget.src = fallbackUrl; else event.currentTarget.style.display = 'none'; }} />}
  </span>;
}

function InfoChip({ label, value, tone }: { label: string; value: number; tone?: 'warning' | 'danger' }) {
  const color = tone === 'warning' ? 'var(--color-warning)' : tone === 'danger' ? 'var(--color-danger)' : 'var(--color-accent)';
  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2"><div className="font-black" style={{ color }}>{value}</div><div className="text-[var(--color-muted)]">{label}</div></div>;
}

function ClientModal({
  client,
  tasks,
  users,
  activity,
  onLoadActivity,
  onClose,
  onSave,
  onDelete,
  permissions,
  isSuperadmin,
}: {
  client: Client | null;
  tasks: Task[];
  users: User[];
  activity: any[];
  onLoadActivity: (clientId: number) => Promise<void>;
  onClose: () => void;
  onSave: () => Promise<void>;
  onDelete?: () => Promise<void>;
  permissions: Record<string, boolean>;
  isSuperadmin: boolean;
}) {
  const [orgName, setOrgName] = useState(client?.org_name || '');
  const [domain, setDomain] = useState(client?.domain || '');
  const [status, setStatus] = useState(client?.status || 'active');
  const [clientWarning, setClientWarning] = useState(client?.client_warning || '');
  const [clientNotes, setClientNotes] = useState(client?.client_notes || '');
  const [competitors, setCompetitors] = useState(client?.competitors || '');
  const [contacts, setContacts] = useState<ContactDraft[]>(client?.contacts?.length ? client.contacts : [{ ...emptyContact }]);
  const [contracts, setContracts] = useState<ContractDraft[]>(client?.contracts?.length ? client.contracts.map(contract => ({ ...contract, start_date: toInputDate(contract.start_date), end_date: toInputDate(contract.end_date) })) : [{ ...emptyContract }]);
  const [accesses, setAccesses] = useState<AccessDraft[]>(client?.accesses?.length ? client.accesses.map((access, index) => ({ id: access.id ?? index + 1, ...access })) : [{ ...emptyAccess, id: 1 }]);
  const [allowedUserIds, setAllowedUserIds] = useState<number[]>(client?.allowed_user_ids || []);
  const [responsibleUserIds, setResponsibleUserIds] = useState<number[]>(client?.responsible_user_ids || []);
  const [modules, setModules] = useState<any[]>([]);
  const [allModules, setAllModules] = useState<any[]>([]);
  const [health, setHealth] = useState<OrganizationHealth | null>(null);
  const [moduleId, setModuleId] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'main' | 'notes' | 'contacts' | 'access' | 'contracts' | 'files' | 'related' | 'activity'>('main');
  const [responsibleSearch, setResponsibleSearch] = useState('');
  const [accessUserSearch, setAccessUserSearch] = useState('');
  const [files, setFiles] = useState<ClientFile[]>([]);
  const [contractFiles, setContractFiles] = useState<Record<number, ClientFile[]>>({});
  const [contractPasteTargetId, setContractPasteTargetId] = useState<number | null>(null);
  const [fileError, setFileError] = useState('');
  const filterUsers = (query: string, selected: number[]) => {
    const needle = query.trim().toLocaleLowerCase('ru-RU');
    return users.filter(user => selected.includes(user.id) || !needle || user.username.toLocaleLowerCase('ru-RU').includes(needle));
  };

  useEffect(() => {
    if (!client) return;
    Promise.all([api.getClientModules(client.id).catch(() => []), api.getModules().catch(() => []), api.getClientHealth(client.id).catch(() => null), api.getClientFiles(client.id).catch(() => [])]).then(async ([clientModules, moduleList, clientHealth, clientFiles]) => {
      setModules(clientModules);
      setAllModules(moduleList);
      setHealth(clientHealth);
      setFiles(clientFiles);
      const filePairs = await Promise.all((client.contracts || []).filter(contract => contract.id).map(async contract => [contract.id, await api.getContractFiles(client.id, contract.id).catch(() => [])] as const));
      setContractFiles(Object.fromEntries(filePairs));
    });
  }, [client]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setSaving(true);
    const primaryContract = contracts.find(contract => contract.start_date || contract.end_date);
    const payload: Record<string, any> = {
      org_name: orgName,
      domain,
      status,
      contract_start: primaryContract?.start_date || null,
      contract_end: primaryContract?.end_date || null,
      client_warning: clientWarning,
      responsible_user_ids: responsibleUserIds,
    };
    if (canSeeTab('notes')) {
      payload.client_notes = clientNotes;
      payload.competitors = competitors;
    }
    if (canSeeTab('contacts')) {
      payload.contacts = contacts.filter(contact => contact.fio || contact.phone || contact.email || contact.position);
    }
    if (canSeeTab('contracts')) {
      payload.contracts = contracts.filter(contract => contract.contract_type || contract.start_date || contract.end_date);
    }
    if (canSeeTab('access')) {
      payload.accesses = accesses.filter(access => access.title || access.url || access.login || access.password).map((access, index) => ({ ...access, id: access.id ?? Date.now() + index }));
      payload.allowed_user_ids = allowedUserIds;
    }
    try {
      if (client) await api.updateClient(client.id, payload);
      else await api.createClient(payload);
      await onSave();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить клиента.');
    } finally {
      setSaving(false);
    }
  };

  const attachModule = async () => {
    if (!client || !moduleId) return;
    await api.addClientModule(client.id, Number(moduleId));
    setModules(await api.getClientModules(client.id));
    setModuleId('');
  };

  const removeModule = async (id: number) => {
    if (!client) return;
    await api.removeClientModule(client.id, id);
    setModules(prev => prev.filter(module => module.id !== id));
  };

  const uploadClientFiles = async (incomingFiles: File[]) => {
    if (!client || !incomingFiles.length) return;
    setFileError('');
    try {
      for (const file of incomingFiles) await api.uploadClientFile(client.id, file);
      setFiles(await api.getClientFiles(client.id));
    } catch (err) {
      setFileError(err instanceof Error ? err.message : 'Не удалось прикрепить файл.');
    }
  };

  const uploadContractFiles = async (contractId: number, incomingFiles: File[]) => {
    if (!client || !incomingFiles.length) return;
    setFileError('');
    try {
      for (const file of incomingFiles) await api.uploadContractFile(client.id, contractId, file);
      setContractFiles(previous => ({ ...previous, [contractId]: [] }));
      const nextFiles = await api.getContractFiles(client.id, contractId);
      setContractFiles(previous => ({ ...previous, [contractId]: nextFiles }));
    } catch (err) {
      setFileError(err instanceof Error ? err.message : 'Не удалось прикрепить файл к договору.');
    }
  };

  const handleContractFileInput = async (contractId: number, event: ChangeEvent<HTMLInputElement>) => {
    await uploadContractFiles(contractId, event.target.files ? Array.from(event.target.files) : []);
    event.target.value = '';
  };

  const handleFileInput = async (event: ChangeEvent<HTMLInputElement>) => {
    await uploadClientFiles(event.target.files ? Array.from(event.target.files) : []);
    event.target.value = '';
  };

  const handlePaste = async (event: ClipboardEvent<HTMLFormElement>) => {
    if (!client) return;
    const pastedFiles = Array.from(event.clipboardData.files);
    if (!pastedFiles.length) return;
    event.preventDefault();
    if (activeTab === 'contracts') {
      if (contractPasteTargetId) await uploadContractFiles(contractPasteTargetId, pastedFiles);
      else setFileError('Кликните по нужному договору и вставьте файл ещё раз.');
      return;
    }
    setActiveTab('files');
    await uploadClientFiles(pastedFiles);
  };

  const removeClientFile = async (fileId: number) => {
    if (!client) return;
    try {
      await api.deleteClientFile(client.id, fileId);
      setFiles(previous => previous.filter(file => file.id !== fileId));
    } catch (err) {
      setFileError(err instanceof Error ? err.message : 'Не удалось удалить файл.');
    }
  };

  const removeContractFile = async (contractId: number, fileId: number) => {
    if (!client) return;
    try {
      await api.deleteClientFile(client.id, fileId);
      setContractFiles(previous => ({ ...previous, [contractId]: (previous[contractId] || []).filter(file => file.id !== fileId) }));
    } catch (err) {
      setFileError(err instanceof Error ? err.message : 'Не удалось удалить файл договора.');
    }
  };

  const extendContract = (index: number, months: number) => {
    const contract = contracts[index];
    const base = contract.end_date || contract.start_date || isoDate(new Date());
    const next = new Date(`${base}T12:00:00`);
    next.setMonth(next.getMonth() + months);
    updateItem(contracts, setContracts, index, { end_date: isoDate(next), status: 'active' });
  };

  const canSeeTab = (tab: string) => isSuperadmin || permissions.all || tab === 'main' || tab === 'files' || Boolean(permissions[`client_tab_${tab}`]);
  const tabs = [
    { id: 'main', label: 'Обзор' },
    { id: 'notes', label: 'Заметки' },
    { id: 'contacts', label: 'Контакты' },
    { id: 'access', label: 'Доступы' },
    { id: 'contracts', label: 'Договоры' },
    { id: 'files', label: 'Файлы' },
    { id: 'related', label: 'Задачи и модули' },
    { id: 'activity', label: 'История' },
  ] as const;

  useEffect(() => {
    if (!canSeeTab(activeTab)) setActiveTab('main');
  }, [activeTab, permissions, isSuperadmin]);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={onClose}>
      <form onSubmit={submit} onPaste={handlePaste} className="tf-panel flex h-[92dvh] w-full max-w-6xl flex-col overflow-hidden" onClick={event => event.stopPropagation()}>
        <div className="shrink-0 flex min-h-[74px] items-center justify-between border-b border-[var(--color-border)] px-5 py-4">
          <div>
            <div className="flex min-w-0 items-center gap-2"><FaviconBadge client={client} /><h2 className="truncate text-base font-black">{client ? client.org_name : 'Новый клиент'}</h2></div>
            <p className="text-xs text-[var(--color-text-secondary)]">Основные поля всегда на виду, дополнительные вещи разнесены по вкладкам.</p>
          </div>
          <button type="button" onClick={onClose} className="tf-button w-9 px-0"><X size={16} /></button>
        </div>

        <div className="shrink-0 border-b border-[var(--color-border)] px-5 py-3">
          <div className="flex min-h-[40px] flex-wrap items-center gap-2">
            {tabs.filter(tab => canSeeTab(tab.id) && (client || (tab.id !== 'related' && tab.id !== 'activity' && tab.id !== 'files'))).map(tab => (
              <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)} className={activeTab === tab.id ? 'rounded-lg bg-[var(--color-accent)] px-3 py-2 text-sm font-semibold text-white' : 'rounded-lg bg-[var(--color-surface-2)] px-3 py-2 text-sm font-semibold text-[var(--color-text-secondary)] hover:text-white'}>
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-scroll p-5">
          {activeTab === 'main' && (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
              <div className="grid gap-4">
                <Panel title="Главное о клиенте">
                  <section className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_180px]">
                    <Field label="Название"><input className="tf-input" value={orgName} onChange={event => setOrgName(event.target.value)} required /></Field>
                    <Field label="Домен"><input className="tf-input" value={domain} onChange={event => setDomain(event.target.value)} placeholder="site.ru" /></Field>
                    <Field label="Статус"><select className="tf-input" value={status} onChange={event => setStatus(event.target.value)}><option value="active">Активный</option><option value="paused">Пауза</option><option value="closed">Закрыт</option></select></Field>
                  </section>
                </Panel>
                <Panel title="Памятка для задач" icon={<AlertTriangle size={16} />}>
                  <textarea
                    className="tf-input min-h-28 resize-y"
                    value={clientWarning}
                    onChange={event => setClientWarning(event.target.value)}
                    placeholder="Например: нельзя обновлять плагин без согласования; не трогать тему; доступ только через VPN..."
                  />
                  <span className="mt-2 block text-xs text-[var(--color-text-secondary)]">Эта памятка автоматически показывается в задачах клиента, чтобы важное не потерялось.</span>
                </Panel>
              </div>
              <aside className="grid content-start gap-4">
                {client && health && <HealthPanel health={health} />}
                <Panel title="Ответственные" icon={<UserRoundCheck size={16} />}>
                  <p className="mb-3 text-sm text-[var(--color-text-secondary)]">Клиент останется в разделе «Мои», даже если сейчас по нему нет активных задач.</p>
                  <label className="relative mb-3 block">
                    <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" />
                    <input className="tf-input tf-input-icon" value={responsibleSearch} onChange={event => setResponsibleSearch(event.target.value)} placeholder="Найти ответственного" />
                  </label>
                  <div className="grid grid-cols-1 gap-2">
                    {filterUsers(responsibleSearch, responsibleUserIds).map(user => (
                      <label key={user.id} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm">
                        <input type="checkbox" checked={responsibleUserIds.includes(user.id)} onChange={() => setResponsibleUserIds(prev => prev.includes(user.id) ? prev.filter(item => item !== user.id) : [...prev, user.id])} />
                        <span>{user.username}</span>
                      </label>
                    ))}
                    {users.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Список сотрудников недоступен.</div>}
                  </div>
                </Panel>
              </aside>
            </div>
          )}

          {activeTab === 'notes' && canSeeTab('notes') && (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
              <Panel title="Конкуренты" icon={<Target size={16} />}>
                <textarea
                  className="tf-input min-h-56 resize-y text-sm leading-6"
                  value={competitors}
                  onChange={event => setCompetitors(event.target.value)}
                  placeholder={'Например:\nsite-a.ru — сильные статьи и структура услуг\nsite-b.ru — хорошие коммерческие страницы\nsite-c.ru — следить за ценами и офферами'}
                />
                <p className="mt-2 text-xs text-[var(--color-text-secondary)]">Это поле хранится только в клиенте и не показывается в задачах.</p>
              </Panel>
              <aside className="grid content-start gap-4">
                <Panel title="Рабочие заметки" icon={<NotebookText size={16} />}>
                  <textarea
                    className="tf-input min-h-56 resize-y text-sm leading-6"
                    value={clientNotes}
                    onChange={event => setClientNotes(event.target.value)}
                    placeholder="Любые внутренние заметки: особенности согласований, кому писать, что проверять перед работами, нестандартные правила клиента..."
                  />
                </Panel>
                <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 text-sm leading-6 text-[var(--color-text-secondary)]">
                  <div className="mb-1 font-bold text-[var(--color-text)]">Для чего эта вкладка</div>
                  <p>Здесь можно держать справочную информацию по клиенту: конкурентов, идеи, договоренности и наблюдения. В задачах это не появляется, чтобы не перегружать работу исполнителя.</p>
                </div>
              </aside>
            </div>
          )}

          {activeTab === 'contacts' && canSeeTab('contacts') && (
            <EditableList title="Контакты" onAdd={() => setContacts(prev => [...prev, { ...emptyContact }])}>
              {contacts.map((contact, index) => (
                <div key={index} className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
                  <input className="tf-input" placeholder="ФИО" value={contact.fio} onChange={event => updateItem(contacts, setContacts, index, { fio: event.target.value })} />
                  <input className="tf-input" placeholder="Должность" value={contact.position} onChange={event => updateItem(contacts, setContacts, index, { position: event.target.value })} />
                  <input className="tf-input" placeholder="Телефон" value={contact.phone} onChange={event => updateItem(contacts, setContacts, index, { phone: event.target.value })} />
                  <input className="tf-input" placeholder="Email" value={contact.email} onChange={event => updateItem(contacts, setContacts, index, { email: event.target.value })} />
                  <RemoveButton onClick={() => setContacts(prev => prev.filter((_, i) => i !== index))} />
                </div>
              ))}
            </EditableList>
          )}

          {activeTab === 'access' && canSeeTab('access') && (
            <div className="grid gap-4">
              <Panel title="Команда с доступом к клиенту">
                <label className="relative mb-3 block max-w-md">
                  <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" />
                  <input className="tf-input tf-input-icon" value={accessUserSearch} onChange={event => setAccessUserSearch(event.target.value)} placeholder="Найти сотрудника" />
                </label>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                  {filterUsers(accessUserSearch, allowedUserIds).map(user => (
                    <label key={user.id} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm">
                      <input type="checkbox" checked={allowedUserIds.includes(user.id)} onChange={() => setAllowedUserIds(prev => prev.includes(user.id) ? prev.filter(item => item !== user.id) : [...prev, user.id])} />
                      <span>{user.username}</span>
                    </label>
                  ))}
                  {users.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Список сотрудников недоступен.</div>}
                </div>
              </Panel>

              <EditableList title="Доступы" icon={<KeyRound size={16} />} onAdd={() => setAccesses(prev => [...prev, { ...emptyAccess, id: Date.now() }])}>
                {accesses.map((access, index) => (
                  <div key={index} className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_1.4fr_1fr_1fr_auto]">
                    <input className="tf-input" placeholder="Название" value={access.title} onChange={event => updateItem(accesses, setAccesses, index, { title: event.target.value })} />
                    <input className="tf-input" placeholder="URL" value={access.url} onChange={event => updateItem(accesses, setAccesses, index, { url: event.target.value })} />
                    <input className="tf-input" placeholder="Логин" value={access.login} onChange={event => updateItem(accesses, setAccesses, index, { login: event.target.value })} />
                    <input className="tf-input" placeholder="Пароль" value={access.password} onChange={event => updateItem(accesses, setAccesses, index, { password: event.target.value })} />
                    <RemoveButton onClick={() => setAccesses(prev => prev.filter((_, i) => i !== index))} />
                  </div>
                ))}
              </EditableList>
            </div>
          )}

          {activeTab === 'contracts' && canSeeTab('contracts') && (
            <EditableList title="Договоры" onAdd={() => setContracts(prev => [...prev, { ...emptyContract }])}>
              {fileError && <div className="rounded-lg border border-[var(--color-danger)]/45 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">{fileError}</div>}
              {contracts.map((contract, index) => (
                <div key={contract.id || index} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3" onClick={() => contract.id && setContractPasteTargetId(contract.id)}>
                  <div className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(180px,1fr)_150px_150px_130px_auto]">
                    <input className="tf-input" list="contract-type-options" placeholder="Тип договора" value={contract.contract_type} onChange={event => updateItem(contracts, setContracts, index, { contract_type: event.target.value })} />
                    <input className="tf-input" type="date" value={contract.start_date} onChange={event => updateItem(contracts, setContracts, index, { start_date: event.target.value })} />
                    <input className="tf-input" type="date" value={contract.end_date} onChange={event => updateItem(contracts, setContracts, index, { end_date: event.target.value })} />
                    <select className="tf-input" value={contract.status} onChange={event => updateItem(contracts, setContracts, index, { status: event.target.value })}><option value="active">Активен</option><option value="expired">Истёк</option><option value="closed">Закрыт</option></select>
                    <RemoveButton onClick={() => setContracts(prev => prev.filter((_, i) => i !== index))} />
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
                    <span className="text-xs font-semibold text-[var(--color-text-secondary)]">Продлить до:</span>
                    <button type="button" className="tf-button h-8 px-2 text-xs" onClick={() => extendContract(index, 1)}>+1 мес</button>
                    <button type="button" className="tf-button h-8 px-2 text-xs" onClick={() => extendContract(index, 3)}>+3 мес</button>
                    <button type="button" className="tf-button h-8 px-2 text-xs" onClick={() => extendContract(index, 6)}>+6 мес</button>
                    <button type="button" className="tf-button h-8 px-2 text-xs" onClick={() => extendContract(index, 12)}>+1 год</button>
                    <span className="text-xs text-[var(--color-muted)]">Меняет дату окончания, потом нажмите “Сохранить”.</span>
                  </div>
                  <div className="mt-3 rounded-lg border border-dashed border-[var(--color-border)] bg-black/10 p-3">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div className="text-xs font-semibold text-[var(--color-text-secondary)]">Файлы договора{contractPasteTargetId === contract.id && <span className="ml-2 text-[var(--color-accent)]">Ctrl+V прикрепит сюда</span>}</div>
                      {contract.id ? (
                        <label className="tf-button h-8 px-2 text-xs"><Upload size={14} />Прикрепить<input type="file" multiple className="hidden" onChange={event => handleContractFileInput(contract.id!, event)} /></label>
                      ) : (
                        <span className="text-xs text-[var(--color-muted)]">Сохраните клиента, чтобы прикреплять файлы.</span>
                      )}
                    </div>
                    {contract.id && (
                      <div className="grid gap-2 md:grid-cols-2">
                        {(contractFiles[contract.id] || []).map(file => {
                          const href = api.getClientFileUrl(client!.id, file.id);
                          return <div key={file.id} className="flex min-w-0 items-center gap-2 rounded-md bg-[var(--color-surface)] px-2 py-2 text-sm">
                            <Paperclip size={14} className="shrink-0 text-[var(--color-muted)]" />
                            <a href={href} target="_blank" className="min-w-0 flex-1 truncate text-[var(--color-accent)]">{file.name}</a>
                            <span className="shrink-0 text-xs text-[var(--color-muted)]">{Math.ceil((file.size || 0) / 1024)} КБ</span>
                            <button type="button" onClick={() => removeContractFile(contract.id!, file.id)} className="shrink-0 text-[var(--color-muted)] hover:text-[var(--color-danger)]"><Trash2 size={14} /></button>
                          </div>;
                        })}
                        {!(contractFiles[contract.id] || []).length && <div className="text-xs text-[var(--color-muted)]">Файлов у договора пока нет.</div>}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <datalist id="contract-type-options">
                {contractTypeOptions.map(type => <option key={type} value={type} />)}
              </datalist>
            </EditableList>
          )}

          {activeTab === 'files' && canSeeTab('files') && client && (
            <Panel icon={<Paperclip size={16} />} title="Файлы организации" action={<label className="tf-button"><Upload size={15} />Прикрепить<input type="file" multiple className="hidden" onChange={handleFileInput} /></label>}>
              <div className="space-y-3">
                <div className="rounded-lg border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-2)] px-3 py-3 text-sm text-[var(--color-text-secondary)]">Здесь можно хранить документы, скриншоты, договоры и другие материалы организации. Скриншот можно вставить прямо в это окно через Ctrl+V.</div>
                {fileError && <div className="text-sm text-[var(--color-danger)]">{fileError}</div>}
                <div className="grid gap-2 md:grid-cols-2">
                  {files.map(file => {
                    const href = api.getClientFileUrl(client.id, file.id);
                    const isImage = (file.content_type || '').startsWith('image/');
                    return <div key={file.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
                      {isImage && <a href={href} target="_blank"><img src={href} alt={file.name} className="mb-2 h-28 w-full rounded object-cover" /></a>}
                      <div className="flex items-center gap-2"><Paperclip size={14} className="text-[var(--color-muted)]" /><a className="min-w-0 flex-1 truncate text-sm text-[var(--color-accent)]" href={href} target="_blank">{file.name}</a><span className="text-xs text-[var(--color-muted)]">{Math.ceil((file.size || 0) / 1024)} КБ</span><button type="button" onClick={() => removeClientFile(file.id)} className="text-[var(--color-muted)] hover:text-[var(--color-danger)]"><Trash2 size={14} /></button></div>
                    </div>;
                  })}
                  {files.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Файлов пока нет.</div>}
                </div>
              </div>
            </Panel>
          )}

          {activeTab === 'related' && canSeeTab('related') && client && (
            <section className="grid gap-4 xl:grid-cols-2">
              <Panel title="Модули клиента">
                <div className="mb-3 flex gap-2">
                  <select className="tf-input" value={moduleId} onChange={event => setModuleId(event.target.value)}>
                    <option value="">Выбрать модуль</option>
                    {allModules.map(module => <option key={module.id} value={module.id}>{module.name}</option>)}
                  </select>
                  <button type="button" onClick={attachModule} className="tf-button">Подключить</button>
                </div>
                <div className="space-y-2">
                  {modules.map(module => <div key={module.id} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 text-sm"><span className="min-w-0 flex-1 truncate font-semibold">{module.name}</span><button type="button" onClick={() => removeModule(module.id)} className="text-[var(--color-muted)] hover:text-[var(--color-danger)]"><Trash2 size={14} /></button></div>)}
                  {modules.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Модули не подключены.</div>}
                </div>
              </Panel>

              <Panel title="Связанные задачи">
                <div className="max-h-64 space-y-2 overflow-auto">
                  {tasks.map(task => <div key={task.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 text-sm"><div className="font-semibold">#{task.id} {task.title}</div><div className="mt-1 flex gap-2 text-xs text-[var(--color-text-secondary)]"><span style={{ color: statusMeta[task.status as keyof typeof statusMeta]?.color }}>{statusMeta[task.status as keyof typeof statusMeta]?.label || task.status}</span><span>{formatDate(task.completion_date)}</span><span>{formatDate(task.deadline)}</span></div></div>)}
                  {tasks.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Задач по клиенту пока нет.</div>}
                </div>
              </Panel>
            </section>
          )}

          {activeTab === 'activity' && canSeeTab('activity') && client && (
            <Panel title="Активность">
              <button type="button" onClick={() => onLoadActivity(client.id)} className="tf-button mb-3"><Activity size={15} />Показать историю</button>
              <div className="max-h-44 space-y-2 overflow-auto">
                {activity.map(item => <div key={item.id} className="rounded-lg bg-[var(--color-surface-2)] p-2 text-sm"><div>{item.summary || item.action}</div>{item.field_name && <div className="mt-1 break-words text-xs text-[var(--color-text-secondary)]">{item.field_name}: <span className="text-[var(--color-danger)]">{item.old_value || 'пусто'}</span> → <span className="text-[var(--color-success)]">{item.new_value || 'пусто'}</span></div>}<div className="text-xs text-[var(--color-muted)]">{item.created_at}{item.actor ? ` · ${item.actor}` : ''}</div></div>)}
                {activity.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">История появится после загрузки.</div>}
              </div>
            </Panel>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--color-border)] px-5 py-4">
          {error && <div className="mr-auto max-w-md text-sm font-semibold text-[var(--color-danger)]">{error}</div>}
          {client && onDelete && (isSuperadmin || permissions.all || permissions.client_delete) && <button type="button" onClick={onDelete} className="tf-button mr-auto text-[var(--color-danger)]"><Trash2 size={15} />В корзину</button>}
          <button type="button" onClick={onClose} className="tf-button">Отмена</button>
          <button disabled={saving} className="tf-button tf-button-primary"><Save size={15} />{saving ? 'Сохранение...' : 'Сохранить'}</button>
        </div>
      </form>
    </div>
  );
}

function HealthPanel({ health }: { health: OrganizationHealth }) {
  const color = health.level === 'good' ? 'var(--color-success)' : health.level === 'watch' ? 'var(--color-warning)' : 'var(--color-danger)';
  const label = health.level === 'good' ? 'Состояние хорошее' : health.level === 'watch' ? 'Требует внимания' : 'Критическое состояние';
  return (
    <Panel title="Здоровье организации" icon={<Activity size={16} />}>
      <div className="flex flex-wrap items-center gap-4">
        <div className="grid h-16 w-16 shrink-0 place-items-center rounded-full border-4 text-xl font-black" style={{ borderColor: color, color }}>{health.score}</div>
        <div className="min-w-0 flex-1"><div className="font-bold" style={{ color }}>{label}</div><div className="mt-1 text-sm text-[var(--color-text-secondary)]">Активных задач: {health.active_tasks} · Просрочено: {health.overdue_tasks} · Зависло: {health.stale_tasks} · Готово за месяц: {health.done_this_month}</div></div>
      </div>
      {health.reasons.length > 0 && <div className="mt-3 grid gap-1 text-sm text-[var(--color-text-secondary)]">{health.reasons.map(reason => <div key={reason}>• {reason}</div>)}</div>}
    </Panel>
  );
}

function EditableList({ title, icon, onAdd, children }: { title: string; icon?: ReactNode; onAdd: () => void; children: ReactNode }) {
  return <Panel title={title} icon={icon}><div className="space-y-2">{children}</div><button type="button" onClick={onAdd} className="tf-button mt-3"><Plus size={15} />Добавить</button></Panel>;
}

function Panel({ title, icon, action, children }: { title: string; icon?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4"><div className="mb-3 flex items-center justify-between gap-3"><h3 className="flex items-center gap-2 text-sm font-bold">{icon}{title}</h3>{action}</div>{children}</section>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label><span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">{label}</span>{children}</label>;
}

function RemoveButton({ onClick }: { onClick: () => void }) {
  return <button type="button" onClick={onClick} className="tf-button text-[var(--color-danger)]"><Trash2 size={15} /></button>;
}

function updateItem<T>(items: T[], setter: (items: T[]) => void, index: number, patch: Partial<T>) {
  setter(items.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
}

function normalizeUrl(domain: string) {
  return domain.startsWith('http') ? domain : `https://${domain}`;
}

function toInputDate(value?: string | null) {
  if (!value) return '';
  const dateOnly = String(value).match(/^(\d{4}-\d{2}-\d{2})/);
  if (dateOnly) return dateOnly[1];
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toISOString().slice(0, 10);
}
