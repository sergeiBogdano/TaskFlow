import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { DndContext, DragOverlay, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from '@dnd-kit/core';
import { AlertCircle, CalendarDays, ChevronDown, ChevronUp, EyeOff, GripVertical, Search } from 'lucide-react';
import { api } from '../api/client';
import { referenceCache } from '../api/cache';
import { SearchSelect } from '../components/SearchSelect';
import { TaskScopeFilter, taskMatchesScope, type TaskScope } from '../components/TaskScopeFilter';
import { useAuth } from '../hooks/useAuth';
import type { Client, SavedView, Task, User } from '../api/client';
import { cn, formatDate, priorityMeta, statusMeta, taskTypeMeta, workflowStatuses } from '../lib/taskflow';

const TaskModal = lazy(() => import('./Tasks').then(module => ({ default: module.TaskModal })));

function TaskCard({ task, onClick }: { task: Task; onClick: () => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `task-${task.id}`,
    data: { task },
  });
  const priority = priorityMeta[task.priority as keyof typeof priorityMeta] || priorityMeta.medium;
  const style = transform ? { transform: `translate(${transform.x}px, ${transform.y}px)`, zIndex: 50 } : undefined;

  return (
    <article
      ref={setNodeRef}
      style={style}
      onClick={onClick}
      className={cn(
        'relative overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 pl-4 transition-colors hover:border-[var(--color-border-strong)] hover:bg-[var(--color-surface-3)]',
        isDragging && 'opacity-45',
      )}
    >
      <span className="absolute bottom-3 left-0 top-3 w-1.5 rounded-r-full" style={{ background: priority.color }} />
      <div className="mb-2 flex items-start gap-2">
        <button {...listeners} {...attributes} onClick={event => event.stopPropagation()} className="mt-0.5 text-[var(--color-muted)] hover:text-white" aria-label="Перетащить">
          <GripVertical size={15} />
        </button>
        <div className="min-w-0 flex-1">
          <div className="line-clamp-2 text-sm font-semibold">{task.title}</div>
          <div className="mt-1 text-[11px] text-[var(--color-text-secondary)]">#{task.id} · {taskTypeMeta[task.task_type] || task.task_type}</div>
        </div>
        {task.visibility === 'private' && <EyeOff size={14} className="text-[var(--color-muted)]" />}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {task.client && <span className="tf-chip max-w-full truncate">{task.client}</span>}
        {task.client_warning && <span className="tf-chip border-[var(--color-warning)]/45 text-[var(--color-warning)]"><AlertCircle size={12} />Важно</span>}
        <span className="tf-chip" style={{ color: priority.color }}>{priority.label}</span>
        {task.no_contract && <span className="tf-chip border-[var(--color-danger)]/40 text-[var(--color-danger)]">нет договора</span>}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-[var(--color-text-secondary)]">
        <span className="flex items-center gap-1"><CalendarDays size={13} />{formatDate(task.completion_date)}</span>
        <span className="flex items-center gap-1"><CalendarDays size={13} />{formatDate(task.deadline)}</span>
      </div>
    </article>
  );
}

function Column({ status, tasks, collapsed, onToggle, onTaskClick }: {
  status: typeof workflowStatuses[number];
  tasks: Task[];
  collapsed: boolean;
  onToggle: () => void;
  onTaskClick: (task: Task) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const meta = statusMeta[status];
  const Icon = meta.icon;

  return (
    <section ref={setNodeRef} className={cn('flex w-[230px] shrink-0 flex-col rounded-lg border bg-[var(--color-surface)]/92 xl:w-[250px]', collapsed ? 'h-auto' : 'h-[clamp(520px,calc(100dvh-250px),760px)]', isOver ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/8' : 'border-[var(--color-border)]')}>
      <header className={cn('flex items-center gap-2 bg-white/[.018] px-3 py-3', !collapsed && 'border-b border-[var(--color-border)]')}>
        <span className="grid h-7 w-7 place-items-center rounded-lg" style={{ background: meta.soft, color: meta.color }}>
          <Icon size={15} />
        </span>
        <div className="min-w-0 flex-1"><div className="text-sm font-bold">{meta.label}</div><div className="text-[11px] text-[var(--color-muted)]">{tasks.length} задач</div></div>
        <button type="button" onClick={onToggle} className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-[var(--color-muted)] hover:bg-[var(--color-surface-3)] hover:text-white" title={collapsed ? `Развернуть «${meta.label}»` : `Свернуть «${meta.label}»`}>
          {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      </header>
      {!collapsed && <div className="flex-1 space-y-2 overflow-auto p-2">
        {tasks.map(task => <TaskCard key={task.id} task={task} onClick={() => onTaskClick(task)} />)}
        {tasks.length === 0 && (
          <div className="rounded-lg border border-dashed border-[var(--color-border)] p-5 text-center text-xs text-[var(--color-text-secondary)]">
            Перетащите задачу сюда
          </div>
        )}
      </div>}
    </section>
  );
}

type PeriodMode = 'day' | 'month' | 'custom';

function localDateValue(date = new Date()) {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function currentMonthBounds() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  return { start: localDateValue(start), end: localDateValue(end) };
}

export function Kanban() {
  const { user: currentUser } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [search, setSearch] = useState('');
  const [searchDraft, setSearchDraft] = useState('');
  const [clientId, setClientId] = useState('all');
  const [priority, setPriority] = useState('all');
  const currentMonth = currentMonthBounds();
  const [periodStart, setPeriodStart] = useState(currentMonth.start);
  const [periodEnd, setPeriodEnd] = useState(currentMonth.end);
  const [periodMode, setPeriodMode] = useState<PeriodMode>('month');
  const [scope, setScope] = useState<TaskScope>('mine');
  const [scopeUserId, setScopeUserId] = useState('');
  const [collapsedColumns, setCollapsedColumns] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('taskflow-kanban-collapsed') || '[]'));
    } catch {
      return new Set();
    }
  });
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [viewName, setViewName] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const params = new URLSearchParams();
    params.set('scope', scope);
    if (scope === 'user' && scopeUserId) params.set('scope_user_id', scopeUserId);
    const [taskList, clientList, userList, views] = await Promise.all([
      api.getTasks(params.toString()),
      referenceCache.clients().catch(() => []),
      referenceCache.users().catch(() => []),
      referenceCache.savedViews('kanban').catch(() => []),
    ]);
    setTasks(taskList.filter(task => taskMatchesScope(task, currentUser, scope, scopeUserId)));
    setClients(clientList);
    setUsers(userList);
    setSavedViews(views);
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, [scope, scopeUserId, currentUser?.id]);

  useEffect(() => {
    localStorage.setItem('taskflow-kanban-collapsed', JSON.stringify([...collapsedColumns]));
  }, [collapsedColumns]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const visibleTasks = useMemo(() => {
    return tasks.filter(task => {
      if (!workflowStatuses.includes(task.status as any)) return false;
      if (search && !`${task.title} ${task.client || ''} ${task.notes || ''}`.toLowerCase().includes(search.toLowerCase())) return false;
      if (clientId !== 'all' && String(task.client_id || '') !== clientId) return false;
      if (priority !== 'all' && task.priority !== priority) return false;
      if (!task.completion_date) return false;
      const completionDate = task.completion_date.slice(0, 10);
      if (completionDate < periodStart || completionDate > periodEnd) return false;
      return true;
    });
  }, [clientId, periodEnd, periodMode, periodStart, priority, search, tasks]);

  const toggleColumn = (status: string) => {
    setCollapsedColumns(previous => {
      const next = new Set(previous);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  };

  const handleDragEnd = async (event: any) => {
    setActiveTask(null);
    const task = event.active.data.current?.task as Task | undefined;
    const nextStatus = event.over?.id as string | undefined;
    if (!task || !nextStatus || task.status === nextStatus) return;
    await api.moveTask(task.id, nextStatus);
    setTasks(prev => prev.map(item => item.id === task.id ? { ...item, status: nextStatus } : item));
  };

  const saveTask = async (data: Partial<Task>) => {
    if (!selectedTask) return;
    await api.updateTask(selectedTask.id, data);
    setSelectedTask(null);
    await load();
  };

  const deleteSelectedTask = async () => {
    if (!selectedTask) return;
    if (!confirm('Переместить задачу в корзину?')) return;
    await api.deleteTask(selectedTask.id);
    setSelectedTask(null);
    await load();
  };

  const saveCurrentView = async () => {
    const name = viewName.trim();
    if (!name) return;
    const view = await api.createSavedView({ name, view_type: 'kanban', filters: { search, clientId, priority, periodStart, periodEnd, periodMode, scope, scopeUserId } });
    referenceCache.invalidate(['saved-views:kanban']);
    setSavedViews(prev => [view, ...prev]);
    setViewName('');
  };

  const applySavedView = (viewId: string) => {
    const view = savedViews.find(item => item.id === Number(viewId));
    if (!view?.filters) return;
    setSearch(view.filters.search || '');
    setSearchDraft(view.filters.search || '');
    setClientId(view.filters.clientId || 'all');
    setPriority(view.filters.priority || 'all');
    setPeriodStart(view.filters.periodStart || view.filters.periodDate || currentMonthBounds().start);
    setPeriodEnd(view.filters.periodEnd || view.filters.periodDate || currentMonthBounds().end);
    setPeriodMode(['day', 'month', 'custom'].includes(view.filters.periodMode) ? view.filters.periodMode : 'month');
    setScope((view.filters.scope || 'mine') as TaskScope);
    setScopeUserId(view.filters.scopeUserId || view.filters.scope_user_id || '');
  };

  const applySearch = () => {
    setSearch(searchDraft.trim());
  };

  if (loading) return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка канбана...</div>;

  return (
    <DndContext sensors={sensors} onDragStart={event => setActiveTask(event.active.data.current?.task || null)} onDragEnd={handleDragEnd}>
      <div className="mx-auto max-w-[1700px] space-y-4">
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(420px,620px)] xl:items-start">
          <div>
            <h2 className="text-xl font-black">Канбан</h2>
            <p className="text-sm text-[var(--color-text-secondary)]">Перетаскивание меняет статус. Клик открывает полную карточку задачи с файлами, комментариями и доступами клиента.</p>
          </div>
          <TaskScopeFilter
            users={users}
            scope={scope}
            userId={scopeUserId}
            onScopeChange={value => { setScope(value); if (value !== 'user') setScopeUserId(''); }}
            onUserChange={setScopeUserId}
            className="w-full"
          />
        </div>
        <section className="tf-panel-flat space-y-3 p-3">
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-[220px_minmax(180px,1fr)_auto]">
            <select className="tf-input" defaultValue="" onChange={event => applySavedView(event.target.value)}>
              <option value="">Сохранённые виды</option>
              {savedViews.map(view => <option key={view.id} value={view.id}>{view.name}</option>)}
            </select>
            <input className="tf-input" value={viewName} onChange={event => setViewName(event.target.value)} placeholder="Название вида" />
            <button onClick={saveCurrentView} className="tf-button" type="button">Сохранить вид</button>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-[minmax(220px,1fr)_240px_170px_160px_160px_250px]">
            <form onSubmit={event => { event.preventDefault(); applySearch(); }} className="flex min-w-0 items-center gap-2">
            <label className="relative min-w-0 flex-1">
              <Search size={15} className="pointer-events-none absolute left-3 top-[12px] text-[var(--color-muted)]" />
              <input className="tf-input tf-input-icon" value={searchDraft} onChange={event => setSearchDraft(event.target.value)} placeholder="Поиск" />
            </label>
            <button className="tf-button shrink-0" type="submit"><Search size={14} />Найти</button>
            </form>
            <SearchSelect
              value={clientId === 'all' ? '' : clientId}
              options={clients.map(client => ({ value: String(client.id), label: client.org_name, description: client.domain || 'Без домена', searchText: client.domain || '' }))}
              onChange={value => setClientId(value || 'all')}
              emptyLabel="Все клиенты"
              searchPlaceholder="Найти клиента или домен"
            />
            <select className="tf-input" value={priority} onChange={event => setPriority(event.target.value)}>
              <option value="all">Все приоритеты</option>
              {Object.entries(priorityMeta).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}
            </select>
            <label className="relative">
              <CalendarDays size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" />
              <input className="tf-input tf-input-icon" type="date" value={periodStart} aria-label="Дата с" onChange={event => { const value = event.target.value; setPeriodStart(value); if (value > periodEnd) setPeriodEnd(value); setPeriodMode('custom'); }} title="Дата начала периода" />
            </label>
            <label className="relative">
              <CalendarDays size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" />
              <input className="tf-input tf-input-icon" type="date" value={periodEnd} min={periodStart} aria-label="Дата по" onChange={event => { setPeriodEnd(event.target.value); setPeriodMode('custom'); }} title="Дата окончания периода" />
            </label>
            <div className="grid grid-cols-3 gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-1">
              <button type="button" onClick={() => { const today = localDateValue(); setPeriodStart(today); setPeriodEnd(today); setPeriodMode('day'); }} className={cn('rounded-md px-2 py-1.5 text-xs font-semibold', periodMode === 'day' ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]')}>День</button>
              <button type="button" onClick={() => { const month = currentMonthBounds(); setPeriodStart(month.start); setPeriodEnd(month.end); setPeriodMode('month'); }} className={cn('rounded-md px-2 py-1.5 text-xs font-semibold', periodMode === 'month' ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]')}>Месяц</button>
              <button type="button" onClick={() => setPeriodMode('custom')} className={cn('rounded-md px-2 py-1.5 text-xs font-semibold', periodMode === 'custom' ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]')}>Период</button>
            </div>
          </div>
        </section>

        <div className="overflow-x-auto pb-2">
          <div className="flex min-w-max gap-3">
            {workflowStatuses.map(status => (
              <Column
                key={status}
                status={status}
                tasks={visibleTasks.filter(task => task.status === status)}
                collapsed={collapsedColumns.has(status)}
                onToggle={() => toggleColumn(status)}
                onTaskClick={setSelectedTask}
              />
            ))}
          </div>
        </div>
      </div>

      <DragOverlay>
        {activeTask && (
          <div className="w-72 rounded-lg border border-[var(--color-accent)] bg-[var(--color-surface-2)] p-3">
            <div className="text-sm font-semibold">{activeTask.title}</div>
          </div>
        )}
      </DragOverlay>

      {selectedTask && <Suspense fallback={null}><TaskModal task={selectedTask} clients={clients} users={users} onClose={() => setSelectedTask(null)} onSave={saveTask} onDelete={deleteSelectedTask} /></Suspense>}
    </DndContext>
  );
}
