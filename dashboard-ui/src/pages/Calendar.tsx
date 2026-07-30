import { lazy, Suspense, useEffect, useState, type MouseEvent } from 'react';
import { DndContext, DragOverlay, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from '@dnd-kit/core';
import { ChevronLeft, ChevronRight, Plus, Trash2 } from 'lucide-react';
import { api, type Client, type QuickTaskTemplate, type Task, type User } from '../api/client';
import { referenceCache } from '../api/cache';
import { TaskScopeFilter, taskMatchesScope, type TaskScope } from '../components/TaskScopeFilter';
import { useAuth } from '../hooks/useAuth';
import { cn, statusMeta } from '../lib/taskflow';

const TaskModal = lazy(() => import('./Tasks').then(module => ({ default: module.TaskModal })));

type ViewMode = 'day' | 'month' | 'quick';

function DraggableEvent({ event, onClick, opening }: { event: any; onClick: (event: MouseEvent<HTMLDivElement>) => void; opening: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `event-${event.id}`,
    data: { taskId: Number(event.id) },
  });
  const meta = statusMeta[event.status as keyof typeof statusMeta] || statusMeta.todo;

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      onClick={onClick}
      style={{ borderColor: meta.color }}
      className={cn('truncate rounded-md border-l-[14px] bg-[var(--color-surface-2)] px-3 py-2.5 text-xs font-semibold text-[var(--color-text)] shadow-sm', (isDragging || opening) && 'opacity-40')}
    >
      {opening ? 'Открываем задачу...' : event.title}
    </div>
  );
}

function DayCell({ date, day, events, onEventClick, onCreate, onMore, openingTaskId }: { date: string; day: number; events: any[]; onEventClick: (event: any) => void; onCreate: () => void; onMore: () => void; openingTaskId: number | null }) {
  const { setNodeRef, isOver } = useDroppable({ id: `day-${date}`, data: { date } });
  return (
    <div ref={setNodeRef} onDoubleClick={onCreate} className={cn('min-h-[118px] border-r border-b border-[var(--color-border)]/55 p-2 transition-colors', isOver && 'bg-[var(--color-accent)]/10')}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-bold text-[var(--color-text-secondary)]">{day}</span>
        <button onClick={onCreate} className="text-[var(--color-muted)] hover:text-[var(--color-accent)]" title="Создать задачу"><Plus size={13} /></button>
      </div>
      <div className="space-y-1">
        {events.slice(0, 4).map(event => <DraggableEvent key={event.id} event={event} opening={openingTaskId === Number(event.id)} onClick={e => { e.stopPropagation(); onEventClick(event); }} />)}
        {events.length > 4 && <button type="button" onClick={(event) => { event.stopPropagation(); onMore(); }} className="text-[11px] font-semibold text-[var(--color-accent)] hover:text-[var(--color-accent-strong)]">+{events.length - 4} ещё</button>}
      </div>
    </div>
  );
}

export function Calendar() {
  const { user: currentUser } = useAuth();
  const [currentDate, setCurrentDate] = useState(new Date());
  const [view, setView] = useState<ViewMode>('month');
  const [events, setEvents] = useState<any[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [createDate, setCreateDate] = useState<string | null>(null);
  const [quickTitle, setQuickTitle] = useState('');
  const [quickDate, setQuickDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [quickNotice, setQuickNotice] = useState('');
  const [calendarError, setCalendarError] = useState('');
  const [creatingQuickId, setCreatingQuickId] = useState<number | null>(null);
  const [quickTemplates, setQuickTemplates] = useState<QuickTaskTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingTaskId, setOpeningTaskId] = useState<number | null>(null);
  const [draggedEvent, setDraggedEvent] = useState<any | null>(null);
  const [scope, setScope] = useState<TaskScope>('mine');
  const [scopeUserId, setScopeUserId] = useState('');
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const getRange = () => {
    const y = currentDate.getFullYear();
    const m = currentDate.getMonth();
    if (view === 'month') return { start: new Date(y, m, 1).toISOString().slice(0, 10), end: new Date(y, m + 1, 0).toISOString().slice(0, 10) };
    return { start: currentDate.toISOString().slice(0, 10), end: currentDate.toISOString().slice(0, 10) };
  };

  const load = async () => {
    const { start, end } = getRange();
    const scopeQuery = `scope=${encodeURIComponent(scope)}${scope === 'user' && scopeUserId ? `&scope_user_id=${encodeURIComponent(scopeUserId)}` : ''}`;
    const [eventList, clientList, userList, quickList] = await Promise.all([
      api.getCalendarEvents(start, end, undefined, scopeQuery),
      referenceCache.clients().catch(() => []),
      referenceCache.users().catch(() => []),
      api.getQuickTasks().catch(() => []),
    ]);
    setEvents(eventList.filter(event => taskMatchesScope(event as Task, currentUser, scope, scopeUserId)));
    setClients(clientList);
    setUsers(userList);
    setQuickTemplates(quickList);
  };

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, [currentDate, view, scope, scopeUserId, currentUser?.id]);

  const navigateDate = (dir: number) => {
    const next = new Date(currentDate);
    if (view === 'month') next.setMonth(next.getMonth() + dir);
    else next.setDate(next.getDate() + dir);
    setCurrentDate(next);
  };

  const openTask = async (event: any) => {
    const taskId = Number(event.id);
    if (openingTaskId) return;
    setOpeningTaskId(taskId);
    setCalendarError('');
    try {
      const task = await api.getTask(taskId);
      setSelectedTask(task);
    } catch (err) {
      setCalendarError(err instanceof Error ? err.message : 'Не удалось открыть задачу.');
    } finally {
      setOpeningTaskId(null);
    }
  };

  const saveTask = async (data: Partial<Task>) => {
    if (selectedTask) await api.updateTask(selectedTask.id, data);
    else await api.createTask(data);
    setSelectedTask(null);
    setCreateDate(null);
    await load();
  };

  const deleteSelectedTask = async () => {
    if (!selectedTask) return;
    if (!confirm('Переместить задачу в корзину?')) return;
    await api.deleteTask(selectedTask.id);
    setSelectedTask(null);
    setCreateDate(null);
    await load();
  };

  const handleDragEnd = async (event: any) => {
    setDraggedEvent(null);
    const taskId = event.active.data.current?.taskId;
    const date = event.over?.data.current?.date;
    if (!taskId || !date) return;
    const previousEvents = events;
    const currentEvent = events.find(item => Number(item.id) === Number(taskId));
    if ((currentEvent?.date || String(currentEvent?.start || '').slice(0, 10)) === date) return;
    setCalendarError('');
    setEvents(current => current.map(item => Number(item.id) === Number(taskId)
      ? { ...item, date, start: `${date}T12:00:00` }
      : item));
    try {
      await api.updateCalendarEvent(taskId, { completion_date: new Date(`${date}T12:00:00`).toISOString() });
    } catch (err) {
      setEvents(previousEvents);
      setCalendarError(err instanceof Error ? err.message : 'Не удалось перенести задачу.');
    }
  };

  const createTaskForDate = (date: string) => {
    setCreateDate(date);
    setSelectedTask(null);
  };

  const addQuickTemplate = () => {
    const title = quickTitle.trim();
    if (!title) return;
    api.createQuickTask({ title, task_type: 'custom', priority: 'medium' }).then(template => {
      setQuickTemplates(prev => [...prev, template]);
      setQuickTitle('');
    });
  };

  const deleteQuickTemplate = async (id: number) => {
    await api.deleteQuickTask(id);
    setQuickTemplates(prev => prev.filter(template => template.id !== id));
  };

  const createQuickTask = async (template: QuickTaskTemplate) => {
    setCreatingQuickId(template.id);
    setQuickNotice('');
    try {
      const targetDate = new Date(`${quickDate}T12:00:00`);
      await api.createTask({
        title: template.title,
        status: 'todo',
        task_type: template.task_type || 'custom',
        priority: template.priority || 'medium',
        completion_date: targetDate.toISOString(),
      });
      setCurrentDate(targetDate);
      setView('month');
      setQuickNotice(`Добавлено в календарь на ${targetDate.toLocaleDateString('ru-RU')}`);
    } finally {
      setCreatingQuickId(null);
    }
  };

  const monthName = currentDate.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
  if (loading) return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка календаря...</div>;

  const renderMonth = () => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const days = Array.from({ length: new Date(year, month + 1, 0).getDate() }, (_, i) => i + 1);
    const padding = Array.from({ length: (new Date(year, month, 1).getDay() + 6) % 7 }, (_, i) => i);
    return (
      <div className="tf-panel-flat overflow-x-auto">
        <div className="grid min-w-[760px] grid-cols-7 border-b border-[var(--color-border)]">
          {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map(day => <div key={day} className="px-3 py-2 text-center text-xs font-bold text-[var(--color-muted)]">{day}</div>)}
        </div>
        <div className="grid min-w-[760px] grid-cols-7">
          {padding.map(i => <div key={`pad-${i}`} className="min-h-[118px] border-r border-b border-[var(--color-border)]/55" />)}
          {days.map(day => {
            const date = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            return <DayCell key={date} date={date} day={day} events={events.filter(event => (event.date || String(event.start).slice(0, 10)) === date)} onEventClick={openTask} onCreate={() => createTaskForDate(date)} onMore={() => { setCurrentDate(new Date(`${date}T12:00:00`)); setView('day'); }} openingTaskId={openingTaskId} />;
          })}
        </div>
      </div>
    );
  };

  const renderDayList = () => {
    const { start } = getRange();
    return (
      <div className="tf-panel-flat min-h-[420px] p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-bold">{new Date(start).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' })}</h3>
          <button onClick={() => createTaskForDate(start)} className="tf-button"><Plus size={15} />Быстрая задача</button>
        </div>
        <div className="space-y-2">
          {events.map(event => <button key={event.id} onClick={() => openTask(event)} className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-left text-sm hover:border-[var(--color-border-strong)]">{event.title}</button>)}
          {events.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">На эту дату задач нет.</div>}
        </div>
      </div>
    );
  };

  const renderQuickTasks = () => (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_360px]">
      <section className="tf-panel-flat p-4">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold">Быстрые задачи</h3>
            <p className="text-xs text-[var(--color-text-secondary)]">Выберите дату и добавьте шаблон прямо в календарь.</p>
          </div>
          <label className="min-w-44">
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Дата в календаре</span>
            <input className="tf-input" type="date" value={quickDate} onChange={event => setQuickDate(event.target.value)} />
          </label>
        </div>
        {quickNotice && <div className="mb-3 rounded-lg border border-[var(--color-success)]/45 bg-[var(--color-success)]/10 px-3 py-2 text-sm text-[var(--color-success)]">{quickNotice}</div>}
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {quickTemplates.map(template => (
            <div key={template.id} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
              <div className="min-w-0 flex-1 truncate text-sm font-semibold">{template.title}</div>
              <button onClick={() => createQuickTask(template)} disabled={creatingQuickId === template.id} className="tf-button tf-button-primary">
                <Plus size={14} />
                {creatingQuickId === template.id ? '...' : 'В календарь'}
              </button>
              <button onClick={() => deleteQuickTemplate(template.id)} className="tf-button text-[var(--color-danger)]" title="Удалить шаблон"><Trash2 size={14} /></button>
            </div>
          ))}
          {quickTemplates.length === 0 && <div className="text-sm text-[var(--color-text-secondary)]">Список пуст. Добавьте первый шаблон справа.</div>}
        </div>
      </section>

      <aside className="tf-panel-flat p-4">
        <h3 className="mb-3 text-sm font-bold">Новый шаблон</h3>
        <div className="space-y-2">
          <input className="tf-input" value={quickTitle} onChange={event => setQuickTitle(event.target.value)} placeholder="Например: набрать клиента" />
          <button onClick={addQuickTemplate} className="tf-button tf-button-primary w-full"><Plus size={15} />Добавить</button>
        </div>
      </aside>
    </div>
  );

  return (
    <DndContext sensors={sensors} onDragStart={event => setDraggedEvent(events.find(item => `event-${item.id}` === String(event.active.id)) || null)} onDragCancel={() => setDraggedEvent(null)} onDragEnd={handleDragEnd}>
      <div className="mx-auto max-w-[1500px] space-y-4">
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
          <div>
            <h2 className="text-xl font-black">Календарь</h2>
            <p className="text-sm text-[var(--color-text-secondary)]">Задачи показываются по дате выполнения. Перетаскивание меняет дату выполнения, не крайний срок.</p>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(320px,460px)_auto_auto_auto_auto] md:items-center xl:justify-end">
            <TaskScopeFilter
              users={users}
              scope={scope}
              userId={scopeUserId}
              onScopeChange={value => { setScope(value); if (value !== 'user') setScopeUserId(''); }}
              onUserChange={setScopeUserId}
              className="w-full"
            />
            <div className="flex gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1">
              {(['day', 'month', 'quick'] as ViewMode[]).map(item => (
                <button key={item} onClick={() => setView(item)} className={cn('rounded-md px-3 py-1 text-xs font-semibold', view === item ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)]')}>
                  {item === 'day' ? 'День' : item === 'month' ? 'Месяц' : 'Быстрые'}
                </button>
              ))}
            </div>
            <button onClick={() => navigateDate(-1)} className="tf-button w-9 px-0"><ChevronLeft size={18} /></button>
            <span className="min-w-40 text-center text-sm font-bold capitalize">{view === 'month' ? monthName : currentDate.toLocaleDateString('ru-RU')}</span>
            <button onClick={() => navigateDate(1)} className="tf-button w-9 px-0"><ChevronRight size={18} /></button>
          </div>
        </div>
        {calendarError && <div className="rounded-lg border border-[var(--color-danger)]/45 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]">{calendarError}</div>}
        {view === 'month' ? renderMonth() : view === 'quick' ? renderQuickTasks() : renderDayList()}
      </div>
      <DragOverlay>{draggedEvent ? <div className="max-w-64 truncate rounded-md border-l-[14px] border-[var(--color-accent)] bg-[var(--color-surface-2)] px-3 py-2.5 text-xs font-semibold text-[var(--color-text)] shadow-xl">{draggedEvent.title}</div> : null}</DragOverlay>
      {(selectedTask || createDate) && <Suspense fallback={null}><TaskModal task={selectedTask} initialTask={!selectedTask && createDate ? { completion_date: new Date(`${createDate}T12:00:00`).toISOString() } : undefined} clients={clients} users={users} onClose={() => { setSelectedTask(null); setCreateDate(null); }} onSave={(data) => saveTask(selectedTask ? data : { ...data, completion_date: new Date(`${createDate || ''}T12:00:00`).toISOString() })} onDelete={selectedTask ? deleteSelectedTask : undefined} onAfterChange={load} /></Suspense>}
    </DndContext>
  );
}
