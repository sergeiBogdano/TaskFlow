import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ClipboardEvent, type FormEvent, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useHotkeys } from 'react-hotkeys-hook';
import { AlertCircle, CalendarDays, Check, ChevronDown, ChevronRight, Clock3, Copy, ExternalLink, ListFilter, Lock, MessageSquare, Paperclip, Plus, Search, Trash2, Upload, X } from 'lucide-react';
import { api } from '../api/client';
import { referenceCache } from '../api/cache';
import type { Client, SavedView, Task, TaskComment, TaskFile, User } from '../api/client';
import { RichTextEditor } from '../components/RichTextEditor';
import { SearchSelect } from '../components/SearchSelect';
import { TaskScopeFilter, taskMatchesScope, type TaskScope } from '../components/TaskScopeFilter';
import { useAuth } from '../hooks/useAuth';
import { cn, formatDate, formatFullDate, priorityMeta, statusMeta, taskTypeMeta, workflowStatuses } from '../lib/taskflow';

type Filters = { search: string; status: string[]; priority: string; client: string; assignee: string; scope: TaskScope; scopeUserId: string };

const baseFilters: Filters = { search: '', status: [], priority: 'all', client: 'all', assignee: 'all', scope: 'mine', scopeUserId: '' };
const statusOptions = workflowStatuses;

function plainText(value: string) {
  return value.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

export function Tasks() {
  const { user: currentUser } = useAuth();
  const [searchParams] = useSearchParams();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [filters, setFilters] = useState<Filters>({
    ...baseFilters,
    search: searchParams.get('search') || '',
    status: searchParams.get('status') ? searchParams.get('status')!.split(',').filter(Boolean) : [],
    client: searchParams.get('client_id') || 'all',
    assignee: searchParams.get('assignee') || 'all',
    scope: (searchParams.get('scope') as TaskScope) || 'mine',
    scopeUserId: searchParams.get('scope_user_id') || '',
  });
  const [loading, setLoading] = useState(true);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [viewName, setViewName] = useState('');
  const [selectedViewId, setSelectedViewId] = useState('');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkStatus, setBulkStatus] = useState('');
  const [bulkPriority, setBulkPriority] = useState('');
  const [bulkAssignee, setBulkAssignee] = useState('');
  const [bulkCompletionDate, setBulkCompletionDate] = useState('');
  const [bulkDeadline, setBulkDeadline] = useState('');
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkError, setBulkError] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [totalTasks, setTotalTasks] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [searchDraft, setSearchDraft] = useState(searchParams.get('search') || '');
  const [bulkOpen, setBulkOpen] = useState(false);
  const clientOptions = useMemo(() => clients.map(client => ({
    value: String(client.id),
    label: client.org_name,
    description: client.domain || 'Без домена',
    searchText: client.domain || '',
  })), [clients]);
  const userOptions = useMemo(() => users.map(user => ({ value: String(user.id), label: user.username })), [users]);

  const load = async () => {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('page_size', String(pageSize));
    if (filters.search.trim()) params.set('search', filters.search.trim());
    if (filters.status.length) params.set('status', filters.status.join(','));
    if (filters.priority !== 'all') params.set('priority', filters.priority);
    if (filters.client !== 'all') params.set('client_id', filters.client);
    if (filters.assignee !== 'all') params.set('assignee', filters.assignee);
    params.set('scope', filters.scope);
    if (filters.scope === 'user' && filters.scopeUserId) params.set('scope_user_id', filters.scopeUserId);

    const [taskPage, clientList, userList, views] = await Promise.all([
      api.getTasksPage(params.toString()),
      referenceCache.clients().catch(() => []),
      referenceCache.users().catch(() => []),
      referenceCache.savedViews('tasks').catch(() => []),
    ]);
    const scopedItems = taskPage.items.filter(task => taskMatchesScope(task, currentUser, filters.scope, filters.scopeUserId));
    setTasks(scopedItems);
    setTotalTasks(taskPage.total);
    setClients(clientList);
    setUsers(userList);
    setSavedViews(views);
  };

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, [filters, page, pageSize, currentUser?.id]);

  useEffect(() => {
    const status = searchParams.get('status');
    const client = searchParams.get('client_id');
    const assignee = searchParams.get('assignee');
    const search = searchParams.get('search');
    const scope = searchParams.get('scope') as TaskScope | null;
    const scopeUserId = searchParams.get('scope_user_id');
    if (search !== null) setSearchDraft(search);
    setFilters(prev => ({
      ...prev,
      search: search !== null ? search : prev.search,
       status: status ? status.split(',').filter(Boolean) : prev.status,
      client: client || prev.client,
      assignee: assignee || prev.assignee,
      scope: scope || prev.scope,
      scopeUserId: scopeUserId || prev.scopeUserId,
    }));
  }, [searchParams]);

  useEffect(() => {
    const taskId = Number(searchParams.get('task'));
    if (!taskId) return;
    const localTask = tasks.find(task => task.id === taskId);
    if (localTask) {
      setEditingTask(localTask);
      setShowModal(true);
      return;
    }
    api.getTask(taskId).then(task => {
      setEditingTask(task);
      setShowModal(true);
    }).catch(() => undefined);
  }, [searchParams, tasks]);

  useHotkeys('n', () => openCreate(), { preventDefault: true });
  useHotkeys('escape', () => setShowModal(false));

  useEffect(() => {
    setPage(1);
  }, [filters, pageSize]);

  const pageCount = Math.max(1, Math.ceil(totalTasks / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageStart = totalTasks ? (currentPage - 1) * pageSize : 0;
  const pageEnd = Math.min(pageStart + tasks.length, totalTasks);
  const pagedTasks = tasks;
  const activeFilterCount = Number(Boolean(filters.search.trim())) + Number(filters.status.length > 0) + Number(filters.priority !== 'all') + Number(filters.client !== 'all') + Number(filters.assignee !== 'all') + Number(filters.scope !== 'mine') + Number(Boolean(filters.scopeUserId));

  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  const counts = statusOptions.reduce<Record<string, number>>((acc, status) => {
    acc[status] = tasks.filter(task => task.status === status).length;
    return acc;
  }, {});

  const openCreate = () => {
    setEditingTask(null);
    setShowModal(true);
  };

  const openEdit = (task: Task) => {
    setEditingTask(task);
    setShowModal(true);
  };

  const changeStatus = async (task: Task, status: string) => {
    await api.moveTask(task.id, status);
    setTasks(prev => prev.map(item => item.id === task.id ? { ...item, status } : item));
  };

  const saveTask = async (data: Partial<Task>) => {
    if (editingTask) await api.updateTask(editingTask.id, data);
    else await api.createTask(data);
    setShowModal(false);
    setEditingTask(null);
    await load();
  };

  const deleteTask = async () => {
    if (!editingTask) return;
    if (!confirm('Переместить задачу в корзину?')) return;
    await api.deleteTask(editingTask.id);
    setShowModal(false);
    setEditingTask(null);
    await load();
  };

  const saveCurrentView = async () => {
    const name = viewName.trim();
    if (!name) return;
    const view = await api.createSavedView({ name, view_type: 'tasks', filters });
    referenceCache.invalidate(['saved-views:tasks']);
    setSavedViews(prev => [view, ...prev]);
    setViewName('');
    setSelectedViewId(String(view.id));
  };

  const applySavedView = (viewId: string) => {
    setSelectedViewId(viewId);
    const view = savedViews.find(item => item.id === Number(viewId));
    if (view?.filters) {
      const savedStatus = Array.isArray(view.filters.status) ? view.filters.status : (view.filters.status && view.filters.status !== 'all' ? String(view.filters.status).split(',').filter(Boolean) : []);
      setFilters({ ...baseFilters, ...view.filters, status: savedStatus, scope: (view.filters.scope || 'mine') as TaskScope, scopeUserId: view.filters.scopeUserId || view.filters.scope_user_id || '' });
      setSearchDraft(view.filters.search || '');
      setViewName(view.name);
    }
  };

  const applyTaskSearch = () => {
    const value = searchDraft.trim();
    setPage(1);
    setFilters(prev => ({ ...prev, search: value }));
  };

  const resetTaskFilters = () => {
    setSearchDraft('');
    setFilters(baseFilters);
  };

  const updateCurrentView = async () => {
    const viewId = Number(selectedViewId);
    const name = viewName.trim();
    if (!viewId || !name) return;
    const view = await api.updateSavedView(viewId, { name, filters });
    referenceCache.invalidate(['saved-views:tasks']);
    setSavedViews(prev => prev.map(item => item.id === view.id ? view : item));
  };

  const deleteCurrentView = async () => {
    const viewId = Number(selectedViewId);
    if (!viewId) return;
    if (!confirm('Удалить сохранённый вид?')) return;
    await api.deleteSavedView(viewId);
    referenceCache.invalidate(['saved-views:tasks']);
    setSavedViews(prev => prev.filter(item => item.id !== viewId));
    setSelectedViewId('');
    setViewName('');
  };

  const toggleSelected = (id: number) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]);
  };

  const toggleAllFiltered = () => {
    const filteredIds = tasks.map(task => task.id);
    const allSelected = filteredIds.length > 0 && filteredIds.every(id => selectedIds.includes(id));
    setSelectedIds(allSelected ? selectedIds.filter(id => !filteredIds.includes(id)) : Array.from(new Set([...selectedIds, ...filteredIds])));
  };

  const resetBulk = () => {
    setBulkStatus('');
    setBulkPriority('');
    setBulkAssignee('');
    setBulkCompletionDate('');
    setBulkDeadline('');
  };

  const applyBulk = async (deleted = false) => {
    setBulkError('');
    if (!selectedIds.length) {
      setBulkError('Сначала выберите задачи галочками.');
      return;
    }
    const fields: Record<string, any> = {};
    if (deleted) fields.deleted = true;
    if (bulkStatus) fields.status = bulkStatus;
    if (bulkPriority) fields.priority = bulkPriority;
    if (bulkAssignee !== '') fields.assignee_id = bulkAssignee === 'none' ? null : Number(bulkAssignee);
    if (bulkCompletionDate) fields.completion_date = new Date(bulkCompletionDate).toISOString();
    if (bulkDeadline) fields.deadline = new Date(bulkDeadline).toISOString();
    if (!Object.keys(fields).length) {
      setBulkError('Выберите, что изменить: статус, приоритет, исполнителя или даты.');
      return;
    }
    if (deleted && !confirm(`Переместить в корзину выбранные задачи: ${selectedIds.length}?`)) return;
    setBulkSaving(true);
    try {
      await api.bulkUpdateTasks(selectedIds, fields);
      setSelectedIds([]);
      resetBulk();
      await load();
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : 'Не удалось применить массовые изменения.');
    } finally {
      setBulkSaving(false);
    }
  };

  if (loading) return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка задач...</div>;

  return (
    <div className="mx-auto max-w-[1500px] space-y-5">
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(360px,520px)_auto] xl:items-start">
        <div>
          <h2 className="text-xl font-black">Задачи</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">Дата постановки берётся из создания. Дата выполнения — когда планируете сесть за задачу. Крайний срок — последний допустимый день.</p>
        </div>
        <TaskScopeFilter
          users={users}
          scope={filters.scope}
          userId={filters.scopeUserId}
          onScopeChange={scope => setFilters(prev => ({ ...prev, scope, scopeUserId: scope === 'user' ? prev.scopeUserId : '' }))}
          onUserChange={scopeUserId => setFilters(prev => ({ ...prev, scopeUserId }))}
          className="w-full"
        />
        <div className="flex flex-wrap gap-2 xl:justify-end">
          <button type="button" onClick={() => setFiltersOpen(previous => !previous)} className={filtersOpen || activeFilterCount ? 'tf-button tf-button-primary' : 'tf-button'}><ListFilter size={15} />Фильтры{activeFilterCount > 0 ? ` · ${activeFilterCount}` : ''}</button>
          <button onClick={openCreate} className="tf-button tf-button-primary"><Plus size={16} />Новая задача</button>
        </div>
      </div>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {statusOptions.map(status => {
          const meta = statusMeta[status as keyof typeof statusMeta] || statusMeta.todo;
          return (
            <button key={status} onClick={() => setFilters(prev => ({ ...prev, status: prev.status.length === 1 && prev.status[0] === status ? [] : [status] }))} className={cn('tf-panel-flat p-3 text-left hover:border-[var(--color-border-strong)]', filters.status.includes(status) && 'border-[var(--color-accent)]')}>
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]"><span className="h-4 w-4 rounded-full" style={{ background: meta.color }} />{meta.label}</div>
              <div className="mt-2 text-2xl font-black">{counts[status] || 0}</div>
            </button>
          );
        })}
      </section>

      {filtersOpen && <section className="tf-panel-flat space-y-3 p-4">
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(260px,360px)]">
          <div className="grid grid-cols-1 gap-2 md:grid-cols-[220px_minmax(0,1fr)]">
            <select className="tf-input" value={selectedViewId} onChange={event => applySavedView(event.target.value)}>
              <option value="">Сохранённые представления</option>
              {savedViews.map(view => <option key={view.id} value={view.id}>{view.name}</option>)}
            </select>
            <input className="tf-input" value={viewName} onChange={event => setViewName(event.target.value)} placeholder="Название нового представления" />
          </div>
          <div className="flex flex-wrap gap-2 xl:justify-end">
            <button onClick={saveCurrentView} className="tf-button" type="button">Сохранить вид</button>
            <button onClick={updateCurrentView} disabled={!selectedViewId || !viewName.trim()} className="tf-button" type="button">Обновить</button>
            <button onClick={deleteCurrentView} disabled={!selectedViewId} className="tf-button text-[var(--color-danger)]" type="button"><Trash2 size={15} />Удалить</button>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-[minmax(260px,1.3fr)_190px_220px_220px_110px]">
          <div className="relative rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
            <div className="mb-1 text-xs font-semibold text-[var(--color-text-secondary)]">Статусы{filters.status.length ? ` · выбрано ${filters.status.length}` : ' · все'}</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              {statusOptions.map(status => <label key={status} className="flex min-w-0 items-center gap-2 text-xs"><input type="checkbox" checked={filters.status.includes(status)} onChange={() => setFilters(prev => ({ ...prev, status: prev.status.includes(status) ? prev.status.filter(item => item !== status) : [...prev.status, status] }))} className="accent-[var(--color-accent)]" /><span className="truncate">{statusMeta[status as keyof typeof statusMeta]?.label || status}</span></label>)}
            </div>
          </div>
          <select className="tf-input" value={filters.priority} onChange={event => setFilters(prev => ({ ...prev, priority: event.target.value }))}>
            <option value="all">Все приоритеты</option>
            {Object.entries(priorityMeta).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}
          </select>
          <SearchSelect value={filters.client === 'all' ? '' : filters.client} options={clientOptions} onChange={value => setFilters(prev => ({ ...prev, client: value || 'all' }))} emptyLabel="Все клиенты" searchPlaceholder="Найти клиента или домен" />
          <SearchSelect value={filters.assignee === 'all' ? '' : filters.assignee} options={userOptions} onChange={value => setFilters(prev => ({ ...prev, assignee: value || 'all' }))} emptyLabel="Все исполнители" searchPlaceholder="Найти сотрудника" />
          <button onClick={resetTaskFilters} className="tf-button"><ListFilter size={15} />Сброс</button>
        </div>
      </section>}

      <section className="tf-panel-flat p-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" checked={tasks.length > 0 && tasks.every(task => selectedIds.includes(task.id))} onChange={toggleAllFiltered} />
            Выбрано: {selectedIds.length}
          </label>
          <div className="min-w-[220px] flex-1">
            <div className="text-sm font-bold">Массовые изменения</div>
            <div className="text-xs text-[var(--color-text-secondary)]">Сначала отметьте задачи галочками, затем выберите действие.</div>
          </div>
          <button type="button" onClick={() => setBulkOpen(prev => !prev)} className={bulkOpen || selectedIds.length ? 'tf-button tf-button-primary' : 'tf-button'}>{bulkOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}{bulkOpen ? 'Скрыть' : 'Изменить'}</button>
          <button onClick={() => { setSelectedIds([]); setBulkError(''); }} className="tf-button" disabled={!selectedIds.length}>Снять выбор</button>
        </div>
        {bulkOpen && <>
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-[150px_150px_190px_160px_160px_auto_auto]">
          <label className="space-y-1">
            <span className="block text-[11px] font-bold uppercase text-[var(--color-muted)]">Новый статус</span>
            <select className="tf-input" value={bulkStatus} onChange={event => setBulkStatus(event.target.value)}>
              <option value="">Не менять</option>
              {statusOptions.map(status => <option key={status} value={status}>{statusMeta[status as keyof typeof statusMeta]?.label || status}</option>)}
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-[11px] font-bold uppercase text-[var(--color-muted)]">Приоритет</span>
            <select className="tf-input" value={bulkPriority} onChange={event => setBulkPriority(event.target.value)}>
              <option value="">Не менять</option>
              {Object.entries(priorityMeta).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-[11px] font-bold uppercase text-[var(--color-muted)]">Исполнитель</span>
            <SearchSelect
              value={bulkAssignee}
              options={[{ value: 'none', label: 'Не назначен' }, ...userOptions]}
              onChange={setBulkAssignee}
              emptyLabel="Не менять"
              searchPlaceholder="Найти сотрудника"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-[11px] font-bold uppercase text-[var(--color-muted)]">Дата выполнения</span>
            <input className="tf-input" type="date" value={bulkCompletionDate} onChange={event => setBulkCompletionDate(event.target.value)} />
          </label>
          <label className="space-y-1">
            <span className="block text-[11px] font-bold uppercase text-[var(--color-muted)]">Крайний срок</span>
            <input className="tf-input" type="date" value={bulkDeadline} onChange={event => setBulkDeadline(event.target.value)} />
          </label>
          <button onClick={() => applyBulk(false)} disabled={!selectedIds.length || bulkSaving} className="tf-button tf-button-primary self-end">Применить</button>
          <button onClick={() => applyBulk(true)} disabled={!selectedIds.length || bulkSaving} className="tf-button self-end text-[var(--color-danger)]"><Trash2 size={15} />В корзину</button>
        </div>
        {bulkError && <div className="mt-2 text-xs font-semibold text-[var(--color-danger)]">{bulkError}</div>}
        </>}
      </section>

      <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--color-text-secondary)]">
        <span className="font-semibold text-[var(--color-text)]">Показано {totalTasks ? pageStart + 1 : 0}-{pageEnd} из {totalTasks}</span>
        <select className="tf-input w-auto py-1.5 text-xs" value={pageSize} onChange={event => setPageSize(Number(event.target.value))}>
          <option value={25}>25 на странице</option>
          <option value={50}>50 на странице</option>
          <option value={100}>100 на странице</option>
        </select>
        <form onSubmit={event => { event.preventDefault(); applyTaskSearch(); }} className="flex min-w-[280px] flex-1 items-center gap-2">
          <label className="relative min-w-[220px] flex-1">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" />
            <input className="tf-input tf-input-icon py-1.5 text-xs" value={searchDraft} onChange={event => setSearchDraft(event.target.value)} placeholder="Поиск по задачам" />
          </label>
          <button className="tf-button py-1.5 text-xs" type="submit"><Search size={14} />Найти</button>
        </form>
        <button className="tf-button ml-auto" type="button" disabled={currentPage <= 1} onClick={() => setPage(prev => Math.max(1, prev - 1))}>Назад</button>
        <span className="text-xs font-semibold">Страница {currentPage} из {pageCount}</span>
        <button className="tf-button" type="button" disabled={currentPage >= pageCount} onClick={() => setPage(prev => Math.min(pageCount, prev + 1))}>Вперёд</button>
      </div>

      <section className="tf-panel-flat overflow-hidden">
        <div className="hidden min-w-[1180px] grid-cols-[36px_minmax(260px,1fr)_130px_150px_120px_120px_120px_110px] gap-3 border-b border-[var(--color-border)] px-4 py-3 text-xs font-bold uppercase tracking-wide text-[var(--color-muted)] md:grid">
          <span />
          <span>Задача</span>
          <span>Статус</span>
          <span>Клиент</span>
          <span>Исполнитель</span>
          <span>Выполнить</span>
          <span>Дедлайн</span>
          <span>Приоритет</span>
        </div>
        {pagedTasks.map(task => {
          const priority = priorityMeta[task.priority as keyof typeof priorityMeta] || priorityMeta.medium;
          const status = statusMeta[task.status as keyof typeof statusMeta] || statusMeta.todo;
          const assignee = users.find(user => user.id === task.assignee_id);
          return (
            <div key={task.id} className="grid gap-3 border-b border-[var(--color-border)]/60 px-4 py-4 last:border-b-0 hover:bg-[var(--color-surface-2)] md:min-w-[1180px] md:grid-cols-[36px_minmax(260px,1fr)_130px_150px_120px_120px_120px_110px] md:items-center md:py-3">
              <input type="checkbox" checked={selectedIds.includes(task.id)} onChange={() => toggleSelected(task.id)} />
              <button type="button" onClick={() => openEdit(task)} className="min-w-0 text-left">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm font-semibold">{task.title}</span>
                  {task.client_warning && <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[var(--color-warning)]/50 bg-[var(--color-warning)]/15 px-2 py-0.5 text-[11px] font-bold text-[var(--color-warning)]"><AlertCircle size={12} />Важно</span>}
                </div>
                <div className="mt-1 truncate text-xs text-[var(--color-text-secondary)]">#{task.id} · {taskTypeMeta[task.task_type] || task.task_type}{task.notes ? ` · ${plainText(task.notes)}` : ''}</div>
              </button>
              <select value={task.status} onClick={event => event.stopPropagation()} onChange={event => changeStatus(task, event.target.value)} className="tf-input py-1.5 text-xs md:w-full" style={{ color: status.color }}>
                {statusOptions.map(item => <option key={item} value={item}>{statusMeta[item as keyof typeof statusMeta]?.label || item}</option>)}
              </select>
              <span className="truncate text-sm text-[var(--color-text-secondary)]"><span className="md:hidden">Клиент: </span>{task.client || 'Без клиента'}</span>
              <span className="truncate text-sm text-[var(--color-text-secondary)]"><span className="md:hidden">Исполнитель: </span>{assignee?.username || 'Не назначен'}</span>
              <span className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)]"><CalendarDays size={14} />{formatDate(task.completion_date)}</span>
              <span className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)]"><CalendarDays size={14} />{formatDate(task.deadline)}</span>
              <span className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]"><span className="block h-6 w-6 rounded-full" style={{ backgroundColor: priority.color }} /><span className="md:hidden">{priority.label}</span></span>
            </div>
          );
        })}
        {totalTasks === 0 && <div className="p-10 text-center text-sm text-[var(--color-text-secondary)]">Задач по этим фильтрам нет</div>}
      </section>

      {showModal && <TaskModal task={editingTask} clients={clients} users={users} onClose={() => setShowModal(false)} onSave={saveTask} onDelete={editingTask ? deleteTask : undefined} />}
    </div>
  );
}

export function TaskModal({ task, initialTask, clients, users, onClose, onSave, onDelete, onAfterChange }: {
  task: Task | null;
  initialTask?: Partial<Task>;
  clients: Client[];
  users: User[];
  onClose: () => void;
  onSave: (data: Partial<Task>) => Promise<void>;
  onDelete?: () => Promise<void>;
  onAfterChange?: () => void | Promise<void>;
}) {
  const source = task || initialTask || {};
  const [title, setTitle] = useState(source.title || '');
  const [status, setStatus] = useState(source.status || 'todo');
  const [priority, setPriority] = useState(source.priority || 'medium');
  const [taskType, setTaskType] = useState(source.task_type || 'custom');
  const [clientId, setClientId] = useState(source.client_id ? String(source.client_id) : '');
  const [assigneeId, setAssigneeId] = useState(source.assignee_id ? String(source.assignee_id) : '');
  const [coExecutorIds, setCoExecutorIds] = useState<number[]>(source.co_executor_ids?.length ? source.co_executor_ids : (source.co_executor_id ? [source.co_executor_id] : []));
  const [completionDate, setCompletionDate] = useState(source.completion_date ? source.completion_date.slice(0, 10) : '');
  const [deadline, setDeadline] = useState(source.deadline ? source.deadline.slice(0, 10) : '');
  const [visibility, setVisibility] = useState<'public' | 'private'>(source.visibility || 'public');
  const [noContract, setNoContract] = useState(source.no_contract || false);
  const [notes, setNotes] = useState(source.notes || '');
  const [comment, setComment] = useState(source.comment || '');
  const [contractWarning, setContractWarning] = useState('');
  const [contractEnd, setContractEnd] = useState('');
  const [clientWarning, setClientWarning] = useState(task?.client_warning || '');
  const contractEndRef = useRef('');
  const [clientAccesses, setClientAccesses] = useState<any[]>([]);
  const [selectedAccessIds, setSelectedAccessIds] = useState<number[]>((task?.client_access_ids || []).map(Number));
  const [visiblePasswords, setVisiblePasswords] = useState<Record<number, boolean>>({});
  const [copiedAccess, setCopiedAccess] = useState('');
  const [comments, setComments] = useState<TaskComment[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [commentText, setCommentText] = useState('');
  const [commentDate, setCommentDate] = useState('');
  const [files, setFiles] = useState<TaskFile[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'main' | 'accesses' | 'comments' | 'files' | 'history'>('main');
  const [collapsedSections, setCollapsedSections] = useState({ params: true, people: true, dates: true });
  const [coExecutorSearch, setCoExecutorSearch] = useState('');
  const clientOptions = useMemo(() => clients.map(client => ({
    value: String(client.id),
    label: client.org_name,
    description: client.domain || 'Без домена',
    searchText: client.domain || '',
  })), [clients]);
  const availableAssigneeOptions = useMemo(() => users
    .filter(user => !coExecutorIds.includes(user.id))
    .map(user => ({ value: String(user.id), label: user.username })), [coExecutorIds, users]);
  const visibleCoExecutors = useMemo(() => {
    const query = coExecutorSearch.trim().toLocaleLowerCase('ru-RU');
    return users.filter(user => String(user.id) !== assigneeId && (
      coExecutorIds.includes(user.id) || !query || user.username.toLocaleLowerCase('ru-RU').includes(query)
    ));
  }, [assigneeId, coExecutorIds, coExecutorSearch, users]);

  useEffect(() => {
    if (!clientId) {
      setClientAccesses([]);
      setSelectedAccessIds([]);
      setClientWarning('');
      setContractEnd('');
      return;
    }
    let cancelled = false;
    const loadTaskAccesses = () => task?.id ? api.getTaskAccesses(task.id).catch(() => []) : Promise.resolve([]);
    api.getClient(Number(clientId))
      .then(async client => {
        const clientAccessList = (client.accesses || []).map((access: any, index: number) => ({ id: access.id ?? index + 1, ...access }));
        const taskAccessList = await loadTaskAccesses();
        const byId = new Map<number, any>();
        [...clientAccessList, ...taskAccessList].forEach(access => byId.set(Number(access.id), access));
        if (cancelled) return;
        setClientAccesses(Array.from(byId.values()));
        setClientWarning(client.client_warning || '');
        setContractEnd(client.contract_end || '');
      })
      .catch(async () => {
        const taskAccessList = await loadTaskAccesses();
        if (cancelled) return;
        setClientAccesses(taskAccessList);
        setClientWarning(task?.client_warning || '');
        setContractEnd('');
      });
    return () => { cancelled = true; };
  }, [clientId, task?.id]);

  useEffect(() => {
    const dateToCheck = [completionDate, deadline].filter(Boolean).sort().at(-1) || '';
    if (!clientId || !dateToCheck) {
      setContractWarning('');
      setContractEnd('');
      contractEndRef.current = '';
      return;
    }
    fetch(`/api/clients/${clientId}/contract-check?deadline=${encodeURIComponent(new Date(`${dateToCheck}T12:00:00`).toISOString())}`, { credentials: 'include' })
      .then(r => r.json())
      .then(result => {
        contractEndRef.current = result.contract_end || '';
        setContractEnd(result.contract_end || '');
        setContractWarning(result.valid ? '' : result.message);
      })
      .catch(() => setContractWarning(''));
  }, [clientId, completionDate, deadline]);

  useEffect(() => {
    if (!task) return;
    Promise.all([api.getComments(task.id).catch(() => []), api.getTaskFiles(task.id).catch(() => []), api.getTaskActivity(task.id).catch(() => [])])
      .then(([loadedComments, loadedFiles, loadedActivity]) => {
        setComments(loadedComments);
        setFiles(loadedFiles);
        setActivity(loadedActivity);
      });
  }, [task]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    const missingFields = [
      !title.trim() ? 'название' : '',
      !clientId ? 'клиент' : '',
      !assigneeId ? 'исполнитель' : '',
      !completionDate ? 'дата выполнения' : '',
      !deadline ? 'крайний срок' : '',
    ].filter(Boolean);
    if (missingFields.length) {
      setActiveTab('main');
      setError(`Заполните обязательные поля: ${missingFields.join(', ')}.`);
      return;
    }
    if (assigneeId && coExecutorIds.includes(Number(assigneeId))) {
      setError('Исполнитель и соисполнитель должны быть разными.');
      return;
    }
    if (completionDate && deadline && new Date(completionDate) > new Date(deadline)) {
      setError('Дата выполнения не может быть позже крайнего срока.');
      return;
    }
    if (!noContract && contractEndRef.current) {
      const taskDates = [completionDate, deadline].filter(Boolean).map(value => new Date(`${value}T12:00:00`));
      if (taskDates.some(value => new Date(contractEndRef.current) < value)) {
        setError('Договор истекает раньше дедлайна. Отметьте "Нет договора" или измените сроки.');
        return;
      }
    }
    setSaving(true);
    try {
      await onSave({
        title: title.trim(),
        status,
        priority,
        task_type: taskType,
        client_id: clientId ? Number(clientId) : null,
        assignee_id: assigneeId ? Number(assigneeId) : null,
        co_executor_id: coExecutorIds[0] || null,
        co_executor_ids: coExecutorIds,
        completion_date: completionDate ? new Date(`${completionDate}T12:00:00`).toISOString() : null,
        deadline: deadline ? new Date(`${deadline}T12:00:00`).toISOString() : null,
        visibility,
        no_contract: noContract,
        notes,
        comment,
        client_access_ids: selectedAccessIds,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить задачу');
    } finally {
      setSaving(false);
    }
  };

  const toggleAccess = (id: number) => setSelectedAccessIds(prev => prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]);

  const addComment = async () => {
    if (!task || !plainText(commentText)) return;
    if (commentDate && task.deadline && new Date(commentDate) > new Date(task.deadline.slice(0, 10))) {
      setError('Дата в комментарии не может быть позже крайнего срока.');
      return;
    }
    setError('');
    try {
      const created = await api.addComment(task.id, commentText.trim());
      setComments(prev => [...prev, { id: created.id, user_id: 0, content: created.content, mentions: [], created_at: created.created_at }]);
      setCommentText('');
      if (commentDate) {
        await api.updateCalendarEvent(task.id, { completion_date: new Date(`${commentDate}T12:00:00`).toISOString() });
        setCompletionDate(commentDate);
        await onAfterChange?.();
      }
      setCommentDate('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить комментарий.');
    }
  };

  const uploadFileList = async (incomingFiles: File[]) => {
    if (!task || !incomingFiles.length) return;
    setError('');
    try {
      for (const file of incomingFiles) await api.uploadFile(task.id, file);
      setFiles(await api.getTaskFiles(task.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось прикрепить файл.');
    }
  };

  const uploadFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    await uploadFileList(event.target.files ? Array.from(event.target.files) : []);
    event.target.value = '';
  };

  const pasteFile = async (event: ClipboardEvent<HTMLFormElement>) => {
    if (!task) return;
    const files = Array.from(event.clipboardData.files);
    if (!files.length) return;
    event.preventDefault();
    setActiveTab('files');
    await uploadFileList(files);
  };

  const copyAccessValue = async (value: string, key: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopiedAccess(key);
      window.setTimeout(() => setCopiedAccess(previous => previous === key ? '' : previous), 1600);
    } catch {
      setError('Не удалось скопировать значение.');
    }
  };

  const removeFile = async (fileId: number) => {
    if (!task) return;
    await api.deleteFile(task.id, fileId);
    setFiles(prev => prev.filter(file => file.id !== fileId));
  };

  const tabs = [
    { id: 'main', label: 'Работа' },
    { id: 'accesses', label: 'Доступы' },
    { id: 'comments', label: 'Комментарии' },
    { id: 'files', label: 'Файлы' },
    { id: 'history', label: 'История' },
  ] as const;
  const commentCount = comments.length;
  const fileCount = files.length;
  const toggleSection = (section: keyof typeof collapsedSections) => {
    setCollapsedSections(previous => ({ ...previous, [section]: !previous[section] }));
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/68 p-0 sm:p-4" onClick={onClose}>
      <form onSubmit={submit} onPaste={pasteFile} className="tf-modal-shell flex h-[100dvh] w-full max-w-6xl flex-col overflow-hidden rounded-none sm:h-[calc(100dvh-32px)] sm:rounded-lg" onClick={event => event.stopPropagation()}>
        <div className="shrink-0 flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <div>
            <h2 className="text-base font-black">{task ? 'Редактировать задачу' : 'Новая задача'}</h2>
            {task && <p className="text-xs text-[var(--color-text-secondary)]">#{task.id} · дата постановки: {formatFullDate(task.created_at)}</p>}
          </div>
          <button type="button" onClick={onClose} className="tf-button w-9 px-0"><X size={16} /></button>
        </div>

        <div className="shrink-0 border-b border-[var(--color-border)] px-4 py-3">
          <div className="flex flex-wrap gap-2">
            {tabs.map(tab => (
              <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)} className={cn('rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors', activeTab === tab.id ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)] hover:text-white')}>
                {tab.label}
                {tab.id === 'comments' && commentCount > 0 && <span className="ml-1.5 inline-flex min-w-4 items-center justify-center rounded-full bg-[var(--color-accent)] px-1 text-[10px] leading-4 text-white" aria-label={`Комментариев: ${commentCount}`}>{commentCount}</span>}
                {tab.id === 'files' && fileCount > 0 && <span className="ml-1.5 inline-flex min-w-4 items-center justify-center rounded-full bg-[var(--color-warning)] px-1 text-[10px] leading-4 text-black" aria-label={`Файлов: ${fileCount}`}>{fileCount}</span>}
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-scroll p-4">
          {activeTab === 'main' && (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
              <div className="min-w-0 space-y-4">
                <label>
                  <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Название</span>
                  <input className="tf-input text-base font-semibold" value={title} onChange={event => setTitle(event.target.value)} required autoFocus />
                </label>

                <Panel title="Описание">
                  <RichTextEditor value={notes} onChange={setNotes} minHeightClassName="min-h-52" placeholder="Контекст, ссылки, требования, что считать готовым..." />
                </Panel>

                <Panel title="Выполненные работы">
                  <RichTextEditor value={comment} onChange={setComment} minHeightClassName="min-h-44" placeholder="Что уже сделано по задаче: статьи, описания, правки, ссылки, результаты..." />
                </Panel>
              </div>

              <aside className="min-w-0 space-y-3">
                {clientWarning && (
                  <div className="rounded-lg border border-[var(--color-warning)]/55 bg-[var(--color-warning)]/10 px-3 py-3 text-sm">
                    <div className="flex items-center gap-2 font-black text-[var(--color-warning)]"><AlertCircle size={16} />Памятка клиента</div>
                    <div className="mt-2 whitespace-pre-wrap text-[var(--color-text)]">{clientWarning}</div>
                  </div>
                )}

                {contractWarning && (
                  <div className="rounded-lg border border-[var(--color-warning)]/45 bg-[var(--color-warning)]/10 px-3 py-2 text-sm text-[var(--color-warning)]">
                    {contractWarning}{contractEnd && <span className="block mt-1 font-semibold">Дата окончания договора: {formatDate(contractEnd)}</span>}
                  </div>
                )}

                <CollapsiblePanel title="Параметры" collapsed={collapsedSections.params} onToggle={() => toggleSection('params')} summary={`${statusMeta[status as keyof typeof statusMeta]?.label || status} · ${priorityMeta[priority as keyof typeof priorityMeta]?.label || priority}`}>
                  <div className="grid gap-3">
                    <Field label="Статус"><select className="tf-input" value={status} onChange={event => setStatus(event.target.value)}>{statusOptions.map(item => <option key={item} value={item}>{statusMeta[item as keyof typeof statusMeta]?.label || item}</option>)}</select></Field>
                    <Field label="Приоритет"><select className="tf-input" value={priority} onChange={event => setPriority(event.target.value)}>{Object.entries(priorityMeta).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}</select></Field>
                    <Field label="Тип"><select className="tf-input" value={taskType} onChange={event => setTaskType(event.target.value)}>{Object.entries(taskTypeMeta).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field>
                  </div>
                </CollapsiblePanel>

                <CollapsiblePanel title="Клиент и команда" collapsed={collapsedSections.people} onToggle={() => toggleSection('people')} summary={`${clients.find(client => String(client.id) === clientId)?.org_name || 'Без клиента'} · ${users.find(user => String(user.id) === assigneeId)?.username || 'Не назначен'}`}>
                  <div className="grid gap-3">
                    <Field label="Клиент"><SearchSelect value={clientId} options={clientOptions} onChange={setClientId} emptyLabel="Без клиента" searchPlaceholder="Найти клиента или домен" /></Field>
                    <Field label="Исполнитель"><SearchSelect value={assigneeId} options={availableAssigneeOptions} onChange={value => { setAssigneeId(value); setCoExecutorIds(prev => prev.filter(id => String(id) !== value)); }} emptyLabel="Не назначен" searchPlaceholder="Найти сотрудника" /></Field>
                    <div>
                      <div className="mb-2 text-xs font-semibold text-[var(--color-text-secondary)]">Соисполнители</div>
                      <label className="relative mb-2 block">
                        <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" />
                        <input className="tf-input tf-input-icon" value={coExecutorSearch} onChange={event => setCoExecutorSearch(event.target.value)} placeholder="Найти соисполнителя" />
                      </label>
                      <div className="max-h-40 space-y-1 overflow-auto">
                        {visibleCoExecutors.map(user => (
                          <label key={user.id} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm">
                            <input type="checkbox" checked={coExecutorIds.includes(user.id)} onChange={() => setCoExecutorIds(prev => prev.includes(user.id) ? prev.filter(id => id !== user.id) : [...prev, user.id])} className="accent-[var(--color-accent)]" />
                            <span>{user.username}</span>
                          </label>
                        ))}
                        {visibleCoExecutors.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Сотрудники не найдены.</div>}
                      </div>
                    </div>
                  </div>
                </CollapsiblePanel>

                <CollapsiblePanel title="Сроки" collapsed={collapsedSections.dates} onToggle={() => toggleSection('dates')} summary={`Выполнить: ${completionDate || '-'} · дедлайн: ${deadline || '-'}`}>
                  <div className="grid gap-3">
                    <Field label="Дата выполнения"><input className="tf-input" type="date" value={completionDate} max={deadline || undefined} onChange={event => setCompletionDate(event.target.value)} /></Field>
                    <Field label="Крайний срок"><input className="tf-input" type="date" value={deadline} min={completionDate || undefined} onChange={event => setDeadline(event.target.value)} /></Field>
                    <Field label="Видимость"><select className="tf-input" value={visibility} onChange={event => setVisibility(event.target.value as 'public' | 'private')}><option value="public">Публичная</option><option value="private">Приватная</option></select></Field>
                    <label className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm"><input type="checkbox" checked={noContract} onChange={event => setNoContract(event.target.checked)} className="accent-[var(--color-accent)]" />Нет договора</label>
                  </div>
                </CollapsiblePanel>
              </aside>
            </div>
          )}

          {activeTab === 'accesses' && (
            <Panel icon={<Lock size={16} />} title="Доступы клиента в этой задаче">
              <div className="space-y-2">
                {clientAccesses.map(access => {
                  const selected = selectedAccessIds.includes(Number(access.id));
                  return (
                    <div key={access.id} className={cn('rounded-lg border p-3', selected ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/8' : 'border-[var(--color-border)] bg-[var(--color-surface-2)]')}>
                      <label className="flex items-start gap-2">
                        <input type="checkbox" checked={selected} onChange={() => toggleAccess(Number(access.id))} className="mt-1 accent-[var(--color-accent)]" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-base font-bold">{access.title || access.url || 'Доступ'}</span>
                          <span className="mt-1 flex flex-wrap items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                            <span className="min-w-0 flex-1 truncate">{access.url || 'без URL'} · {access.login || 'без логина'}</span>
                            {access.url && <a href={access.url} target="_blank" rel="noreferrer" onClick={event => event.stopPropagation()} className="tf-button h-8 w-8 shrink-0 px-0" title="Открыть URL в новой вкладке" aria-label="Открыть URL в новой вкладке"><ExternalLink size={15} /></a>}
                          </span>
                        </span>
                      </label>
                      {selected && (
                        <div className="mt-2 space-y-2 rounded bg-black/15 p-3 text-sm text-[var(--color-text-secondary)]">
                          <div className="flex items-center gap-2"><span className="min-w-0 flex-1 break-all">URL: {access.url || '-'}</span>{access.url && <a href={access.url} target="_blank" rel="noreferrer" onClick={event => event.stopPropagation()} className="tf-button h-8 w-8 shrink-0 px-0" title="Открыть URL в новой вкладке" aria-label="Открыть URL в новой вкладке"><ExternalLink size={15} /></a>}</div>
                          <div className="flex items-center gap-2"><span className="min-w-0 flex-1 break-all">Логин: {access.login || '-'}</span>{access.login && <button type="button" onClick={() => void copyAccessValue(access.login, `login-${access.id}`)} className="tf-button h-8 shrink-0 px-2 text-xs" title="Скопировать логин">{copiedAccess === `login-${access.id}` ? <Check size={14} /> : <Copy size={14} />}<span className="hidden sm:inline">{copiedAccess === `login-${access.id}` ? 'Скопировано' : 'Копировать'}</span></button>}</div>
                          {access.password && <div className="flex items-center gap-2"><button type="button" onClick={() => setVisiblePasswords(prev => ({ ...prev, [access.id]: !prev[access.id] }))} className="min-w-0 flex-1 break-all text-left text-[var(--color-accent)]">Пароль: {visiblePasswords[access.id] ? access.password : 'показать'}</button><button type="button" onClick={() => void copyAccessValue(access.password, `password-${access.id}`)} className="tf-button h-8 shrink-0 px-2 text-xs" title="Скопировать пароль">{copiedAccess === `password-${access.id}` ? <Check size={14} /> : <Copy size={14} />}<span className="hidden sm:inline">{copiedAccess === `password-${access.id}` ? 'Скопировано' : 'Копировать'}</span></button></div>}
                        </div>
                      )}
                    </div>
                  );
                })}
                {!clientId && <div className="text-sm text-[var(--color-text-secondary)]">Выберите клиента, чтобы подтянуть его доступы.</div>}
                {clientId && clientAccesses.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">У клиента пока нет сохранённых доступов.</div>}
              </div>
            </Panel>
          )}

          {activeTab === 'comments' && (
            <Panel icon={<MessageSquare size={16} />} title="Комментарии">
              {task ? (
                <>
                  <div className="max-h-44 space-y-2 overflow-auto">
                    {comments.map(commentItem => (
                      <div key={commentItem.id} className="rounded-lg bg-[var(--color-surface-2)] p-2 text-sm">
                        <div className="text-xs text-[var(--color-muted)]">{commentItem.created_at ? new Date(commentItem.created_at).toLocaleString('ru-RU') : 'только что'}</div>
                        <div className="prose prose-invert max-w-none text-sm" dangerouslySetInnerHTML={{ __html: commentItem.content }} />
                      </div>
                    ))}
                    {comments.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Комментариев пока нет.</div>}
                  </div>
                  <div className="mt-3 space-y-2">
                    <RichTextEditor value={commentText} onChange={setCommentText} minHeightClassName="min-h-24" placeholder="Написать комментарий, надиктовать итоги или добавить подробности..." />
                    <div className="flex flex-wrap gap-2">
                    <input className="tf-input w-40" type="date" value={commentDate} onChange={event => setCommentDate(event.target.value)} />
                    <button type="button" onClick={addComment} className="tf-button">Отправить</button>
                  </div>
                  </div>
                </>
              ) : <div className="text-sm text-[var(--color-text-secondary)]">Комментарии появятся после создания задачи.</div>}
            </Panel>
          )}

          {activeTab === 'files' && (
            <Panel icon={<Paperclip size={16} />} title="Файлы и изображения" action={task && <label className="tf-button"><Upload size={15} />Прикрепить<input type="file" multiple className="hidden" onChange={uploadFiles} /></label>}>
              {task ? (
                <div className="space-y-3">
                  <div className="rounded-lg border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-2)] px-3 py-3 text-sm text-[var(--color-text-secondary)]">Можно выбрать файл кнопкой выше или вставить скриншот прямо сюда через Ctrl+V.</div>
                  <div className="grid gap-2 md:grid-cols-2">
                  {files.map(file => {
                    const href = `/api/tasks/${task.id}/files/${file.id}/download`;
                    const isImage = (file.content_type || '').startsWith('image/');
                    return (
                      <div key={file.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
                        {isImage && <a href={href} target="_blank"><img src={href} alt={file.name} className="mb-2 h-28 w-full rounded object-cover" /></a>}
                        <div className="flex items-center gap-2">
                          <Paperclip size={14} className="text-[var(--color-muted)]" />
                          <a className="min-w-0 flex-1 truncate text-sm text-[var(--color-accent)]" href={href} target="_blank">{file.name}</a>
                          <span className="text-xs text-[var(--color-muted)]">{Math.ceil((file.size || 0) / 1024)} КБ</span>
                          <button type="button" onClick={() => removeFile(file.id)} className="text-[var(--color-muted)] hover:text-[var(--color-danger)]"><Trash2 size={14} /></button>
                        </div>
                      </div>
                    );
                  })}
                  {files.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Файлов пока нет.</div>}
                  </div>
                </div>
              ) : <div className="text-sm text-[var(--color-text-secondary)]">Файлы можно прикрепить после создания задачи.</div>}
            </Panel>
          )}

          {activeTab === 'history' && (
            <Panel icon={<Clock3 size={16} />} title="История изменений">
              {task ? (
                <div className="space-y-2">
                  {activity.map(item => <div key={item.id} className="rounded-lg bg-[var(--color-surface-2)] p-3 text-sm"><div>{item.summary || item.action}</div>{item.field_name && <div className="mt-1 break-words text-xs text-[var(--color-text-secondary)]">{item.field_name}: <span className="text-[var(--color-danger)]">{item.old_value || 'пусто'}</span> → <span className="text-[var(--color-success)]">{item.new_value || 'пусто'}</span></div>}<div className="mt-1 text-xs text-[var(--color-muted)]">{item.created_at}{item.actor ? ` · ${item.actor}` : ''}</div></div>)}
                  {activity.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Изменений пока нет.</div>}
                </div>
              ) : <div className="text-sm text-[var(--color-text-secondary)]">История появится после создания задачи.</div>}
            </Panel>
          )}
        </div>

        <div className="shrink-0 border-t border-[var(--color-border)] bg-[var(--color-surface)]/96 px-3 py-2 sm:px-4 sm:py-3">
          {error && (
            <div className="mb-2 flex max-h-24 w-full items-start gap-2 overflow-auto rounded-lg border border-[var(--color-danger)]/45 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span className="min-w-0 break-words">{error}</span>
            </div>
          )}
          <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:items-center">
            {task && onDelete && <button type="button" onClick={onDelete} className="tf-button col-span-2 justify-center text-[var(--color-danger)] sm:col-span-1 sm:mr-auto"><Trash2 size={15} />В корзину</button>}
            <button type="button" onClick={onClose} className="tf-button justify-center sm:ml-auto">Отмена</button>
            <button type="submit" disabled={saving} className="tf-button tf-button-primary justify-center">{saving ? 'Сохраняю...' : 'Сохранить'}</button>
          </div>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="relative block">
      <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">{label}</span>
      {children}
    </label>
  );
}

function Panel({ icon, title, action, children }: { icon?: ReactNode; title: string; action?: ReactNode; children: ReactNode }) {
  return <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4"><div className="mb-3 flex items-center justify-between gap-3"><div className="flex items-center gap-2 text-[var(--color-accent)]">{icon}<h3 className="text-sm font-bold text-[var(--color-text)]">{title}</h3></div>{action}</div>{children}</section>;
}

function CollapsiblePanel({ title, summary, collapsed, onToggle, children }: { title: string; summary: string; collapsed: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        {collapsed ? <ChevronRight size={16} className="shrink-0 text-[var(--color-muted)]" /> : <ChevronDown size={16} className="shrink-0 text-[var(--color-accent)]" />}
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold text-[var(--color-text)]">{title}</span>
          <span className="block truncate text-xs text-[var(--color-text-secondary)]">{summary}</span>
        </span>
        <span className="tf-chip text-[var(--color-muted)]">{collapsed ? 'Показать' : 'Скрыть'}</span>
      </button>
      {!collapsed && <div className="border-t border-[var(--color-border)] p-4">{children}</div>}
    </section>
  );
}
