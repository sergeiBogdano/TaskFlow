import { lazy, Suspense, useEffect, useMemo, useState, type KeyboardEvent } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { DndContext, DragOverlay, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, arrayMove, rectSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  BarChart3,
  Bell,
  CalendarDays,
  CheckSquare,
  CircleUser,
  Columns3,
  PanelLeftClose,
  PanelLeftOpen,
  GripVertical,
  LayoutDashboard,
  LogOut,
  Mic,
  Puzzle,
  Send,
  Settings,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { api } from '../api/client';
import { referenceCache } from '../api/cache';
import type { Client, Task, User, VoiceTaskDraft } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import { cn, roleMeta } from '../lib/taskflow';

const TaskModal = lazy(() => import('../pages/Tasks').then(module => ({ default: module.TaskModal })));

const nav = [
  {
    section: 'Работа',
    items: [
      { to: '/', icon: LayoutDashboard, label: 'Дашборд', hint: 'Обзор команды', permission: 'dashboard' },
      { to: '/tasks', icon: CheckSquare, label: 'Задачи', hint: 'Список и фильтры', permission: 'tasks' },
      { to: '/kanban', icon: Columns3, label: 'Канбан', hint: 'Поток работы', permission: 'kanban' },
      { to: '/calendar', icon: CalendarDays, label: 'Календарь', hint: 'План выполнения', permission: 'calendar' },
      { to: '/notifications', icon: Bell, label: 'Уведомления', hint: 'События', permission: 'notifications' },
      { to: '/trash', icon: Trash2, label: 'Корзина', hint: 'Удалённые задачи', permission: 'tasks' },
    ],
  },
  {
    section: 'Клиенты',
    items: [
      { to: '/clients', icon: Users, label: 'Клиенты', hint: 'CRM и договоры', permission: 'clients' },
      { to: '/modules', icon: Puzzle, label: 'Модули', hint: 'Автоматизация', permission: 'modules' },
      { to: '/reports', icon: BarChart3, label: 'Отчёты', hint: 'Метрики', permission: 'reports' },
    ],
  },
  {
    section: 'Система',
    items: [
      { to: '/users', icon: CircleUser, label: 'Пользователи', hint: 'Роли и доступ', permission: 'users' },
      { to: '/settings', icon: Settings, label: 'Настройки', hint: 'Профиль', permission: 'settings' },
    ],
  },
];

const titles: Record<string, string> = {
  '/': 'Командный обзор',
  '/tasks': 'Задачи',
  '/kanban': 'Канбан',
  '/clients': 'Клиенты',
  '/modules': 'Модули',
  '/calendar': 'Календарь',
  '/notifications': 'Уведомления',
  '/users': 'Пользователи',
  '/reports': 'Отчёты',
  '/trash': 'Корзина',
  '/settings': 'Настройки',
};

type NavItem = typeof nav[number]['items'][number];

function SortableNavItem({ item, unreadCount, compact }: { item: NavItem; unreadCount: number; compact: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.to });
  return (
    <NavLink
      ref={setNodeRef}
      to={item.to}
      end={item.to === '/'}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.35 : 1 }}
      className={({ isActive }) => cn(
        'group flex min-w-[74px] flex-col items-center justify-center gap-1 rounded-lg px-2 py-2 text-center text-xs lg:min-w-0 lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:py-2.5 lg:text-left lg:text-sm',
        compact && 'lg:justify-center lg:px-2',
        isActive
          ? 'bg-[var(--color-accent)]/16 text-white shadow-[0_1px_0_rgba(255,255,255,.07)_inset]'
          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)] hover:text-white',
      )}
    >
      <item.icon size={17} />
      <span className={cn('min-w-0 lg:flex-1', compact && 'lg:hidden')}>
        <span className="block truncate font-medium">{item.label}</span>
        <span className="hidden truncate text-[11px] text-[var(--color-muted)] lg:block">{item.hint}</span>
      </span>
      {item.to === '/notifications' && unreadCount > 0 && <span className="rounded-full bg-[var(--color-danger)] px-1.5 py-0.5 text-[10px] font-bold text-white">{unreadCount > 99 ? '99+' : unreadCount}</span>}
      <button type="button" {...attributes} {...listeners} onClick={event => { event.preventDefault(); event.stopPropagation(); }} className={cn('grid h-7 w-7 shrink-0 place-items-center rounded-md text-[var(--color-muted)] opacity-70 hover:bg-[var(--color-surface-3)] hover:text-white lg:opacity-0 lg:group-hover:opacity-100', compact && 'lg:hidden')} aria-label={`Перетащить ${item.label}`} title={`Перетащить ${item.label}`}>
        <GripVertical size={14} />
      </button>
    </NavLink>
  );
}

export function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, hasRole } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [showIntro, setShowIntro] = useState(() => localStorage.getItem('taskflow:intro-closed') !== '1');
  const [navOrder, setNavOrder] = useState<Record<string, string[]>>({});
  const [activeNavRoute, setActiveNavRoute] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('taskflow:sidebar-collapsed') === '1');
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  useEffect(() => {
    if (!user?.id) return;
    const key = `taskflow:nav-order:${user.id}`;
    try {
      setNavOrder(JSON.parse(localStorage.getItem(key) || '{}'));
    } catch {
      setNavOrder({});
    }
  }, [user?.id]);

  useEffect(() => {
    const load = () => api.getUnreadCount().then(result => setUnreadCount(result.count)).catch(() => {});
    load();
    const intervalId = window.setInterval(load, 30000);
    window.addEventListener('taskflow:notifications-updated', load);
    window.addEventListener('focus', load);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('taskflow:notifications-updated', load);
      window.removeEventListener('focus', load);
    };
  }, []);

  const primaryRole = user?.roles?.[0]?.name || 'executor';
  const role = roleMeta[primaryRole] || roleMeta.executor;
  const isSuperadmin = hasRole('superadmin');
  const canSee = (permission: string, route?: string) => {
    if (isSuperadmin) return true;
    if (route === '/users') return false;
    return Boolean(user?.permissions?.all || user?.permissions?.[permission]);
  };
  const pageTitle = useMemo(() => titles[location.pathname] || 'TaskFlow', [location.pathname]);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const closeIntro = () => {
    localStorage.setItem('taskflow:intro-closed', '1');
    setShowIntro(false);
  };

  const toggleSidebar = () => {
    setSidebarCollapsed(previous => {
      const next = !previous;
      localStorage.setItem('taskflow:sidebar-collapsed', next ? '1' : '0');
      return next;
    });
  };

  const orderedItems = (section: string, items: typeof nav[number]['items']) => {
    const saved = navOrder[section] || [];
    const byRoute = new Map(items.map(item => [item.to, item]));
    return [...saved.filter(route => byRoute.has(route)).map(route => byRoute.get(route)!), ...items.filter(item => !saved.includes(item.to))];
  };

  const handleNavDragEnd = (event: DragEndEvent) => {
    setActiveNavRoute(null);
    const sourceRoute = String(event.active.id);
    const targetRoute = event.over ? String(event.over.id) : '';
    if (!targetRoute || sourceRoute === targetRoute) return;
    const group = nav.find(item => {
      const routes = item.items.map(navItem => navItem.to);
      return routes.includes(sourceRoute) && routes.includes(targetRoute);
    });
    if (!group) return;
    const routes = orderedItems(group.section, group.items).map(item => item.to);
    const sourceIndex = routes.indexOf(sourceRoute);
    const targetIndex = routes.indexOf(targetRoute);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const next = { ...navOrder, [group.section]: arrayMove(routes, sourceIndex, targetIndex) };
    setNavOrder(next);
    if (user?.id) localStorage.setItem(`taskflow:nav-order:${user.id}`, JSON.stringify(next));
  };

  return (
    <div className="min-h-screen">
      <aside className={cn('z-30 w-full overflow-hidden border-b border-[var(--color-border)] bg-[var(--color-sidebar)] px-3 py-2 lg:fixed lg:inset-y-0 lg:left-0 lg:flex lg:flex-col lg:overflow-auto lg:border-b-0 lg:border-r lg:py-3', sidebarCollapsed ? 'lg:w-[76px]' : 'lg:w-[264px]')}>
        <div className="mb-2 flex items-center gap-3 px-2 py-2 lg:mb-4">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-accent)] text-sm font-black text-white">TF</div>
          <div className={cn('min-w-0', sidebarCollapsed && 'lg:hidden')}>
            <div className="text-sm font-bold tracking-wide">TaskFlow</div>
            <div className="text-xs text-[var(--color-text-secondary)]">SEO / dev workspace</div>
          </div>
          <button type="button" onClick={toggleSidebar} className={cn('tf-button ml-auto hidden w-9 px-0 lg:inline-flex', sidebarCollapsed && 'lg:ml-0')} title={sidebarCollapsed ? 'Показать меню' : 'Скрыть меню'} aria-label={sidebarCollapsed ? 'Показать меню' : 'Скрыть меню'}>
            {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>

        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={event => setActiveNavRoute(String(event.active.id))} onDragCancel={() => setActiveNavRoute(null)} onDragEnd={handleNavDragEnd}>
        <nav className={cn('flex gap-2 overflow-x-auto pb-1 lg:block lg:overflow-visible lg:pb-0', sidebarCollapsed ? 'lg:space-y-2' : 'lg:space-y-4')}>
          {nav.map(group => {
            const visibleItems = group.items.filter(item => canSee(item.permission, item.to));
            if (!visibleItems.length) return null;
            return (
              <div key={group.section} className={cn('flex shrink-0 gap-2 lg:block', sidebarCollapsed && 'lg:flex lg:justify-center')}>
                <div className={cn('hidden px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-muted)] lg:block', sidebarCollapsed && 'lg:hidden')}>{group.section}</div>
                <SortableContext items={orderedItems(group.section, visibleItems).map(item => item.to)} strategy={rectSortingStrategy}>
                  <div className={cn('flex gap-2 lg:block lg:space-y-1', sidebarCollapsed && 'lg:w-full')}>
                    {orderedItems(group.section, visibleItems).map(item => <SortableNavItem key={item.to} item={item} unreadCount={unreadCount} compact={sidebarCollapsed} />)}
                  </div>
                </SortableContext>
              </div>
            );
          })}
        </nav>
        <DragOverlay>{activeNavRoute ? <div className="rounded-lg border border-[var(--color-accent)] bg-[var(--color-surface-3)] px-3 py-2 text-sm font-semibold text-white shadow-xl">{nav.flatMap(group => group.items).find(item => item.to === activeNavRoute)?.label}</div> : null}</DragOverlay>
        </DndContext>

        <div className={cn('mt-auto hidden space-y-3 lg:block', sidebarCollapsed && 'lg:hidden')}>
          {user && (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]/86 p-3 shadow-[0_1px_0_rgba(255,255,255,.05)_inset]">
              <div className="flex items-center gap-2">
                <div className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--color-surface-3)] text-xs font-bold">
                  {user.username.slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{user.username}</div>
                  <div className="truncate text-xs text-[var(--color-text-secondary)]">{role.label}</div>
                </div>
              </div>
              <div className="mt-2 text-[11px] leading-4 text-[var(--color-muted)]">{role.hint}</div>
            </div>
          )}
          <button onClick={handleLogout} className="tf-button w-full justify-start text-[var(--color-text-secondary)] hover:text-[var(--color-danger)]">
            <LogOut size={16} />
            Выйти
          </button>
        </div>
      </aside>

      <div className={cn(sidebarCollapsed ? 'lg:pl-[76px]' : 'lg:pl-[264px]')}>
        <header className="sticky top-0 z-20 flex min-h-16 items-center gap-4 border-b border-[var(--color-border)] bg-[var(--color-header)] px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <h1 className="text-lg font-bold">{pageTitle}</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">Быстрая работа команды, задач и клиентов</p>
          </div>
          <button onClick={() => setVoiceOpen(true)} className="tf-button ml-auto w-10 px-0 text-[var(--color-accent)]" aria-label="Голосовая задача">
            <Mic size={16} />
          </button>
          <button onClick={() => navigate('/notifications')} className="tf-button relative w-10 px-0" aria-label="Уведомления">
            <Bell size={16} />
            {unreadCount > 0 && <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-[var(--color-danger)]" />}
          </button>
          <button onClick={handleLogout} className="tf-button w-10 px-0 lg:hidden" aria-label="Выйти">
            <LogOut size={16} />
          </button>
        </header>

        <main className="min-h-[calc(100vh-64px)] p-3 sm:p-6">
          {showIntro && (
            <section className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <h2 className="text-sm font-bold">Коротко о работе в TaskFlow</h2>
                  <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                    Задачи планируются по дате выполнения, дедлайн ограничивает крайний срок, а доступ к клиентам определяет, кто видит связанные задачи и данные.
                  </p>
                </div>
                <button type="button" onClick={closeIntro} className="grid h-8 w-8 place-items-center rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-white" aria-label="Закрыть">
                  <X size={15} />
                </button>
              </div>
            </section>
          )}
          <Outlet />
        </main>
      </div>
      {voiceOpen && <VoiceTaskAssistant onClose={() => setVoiceOpen(false)} />}
    </div>
  );
}

function VoiceTaskAssistant({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const [draft, setDraft] = useState<VoiceTaskDraft>({});
  const [questions, setQuestions] = useState<string[]>([]);
  const [modalDraft, setModalDraft] = useState<VoiceTaskDraft | null>(null);
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState('');
  const [createdTask, setCreatedTask] = useState<Task | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    Promise.all([referenceCache.clients().catch(() => []), referenceCache.users().catch(() => [])]).then(([clientList, userList]) => {
      setClients(clientList);
      setUsers(userList);
    });
  }, []);

  const startListening = () => {
    const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Recognition) {
      setError('Браузер не поддерживает распознавание речи. Можно ввести команду текстом.');
      return;
    }
    const recognition = new Recognition();
    recognition.lang = 'ru-RU';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => setListening(true);
    recognition.onerror = () => {
      setListening(false);
      setError('Не удалось распознать голос. Попробуйте еще раз или введите текстом.');
    };
    recognition.onend = () => setListening(false);
    recognition.onresult = (event: any) => {
      const spoken = event.results?.[0]?.[0]?.transcript || '';
      setText(prev => [prev, spoken].filter(Boolean).join(' ').trim());
    };
    recognition.start();
  };

  const analyze = async () => {
    const command = text.trim();
    if (!command) return;
    setLoading(true);
    setError('');
    try {
      const result = await api.parseVoiceTask(command, draft);
      setDraft(result.draft);
      setQuestions([]);
      setModalDraft(result.draft);
      setText('');
    } catch (err: any) {
      setError(err instanceof Error ? err.message : 'Не удалось разобрать команду.');
    } finally {
      setLoading(false);
    }
  };

  const missingForDraft = (value: VoiceTaskDraft) => {
    const missing = [];
    if (!value.title) missing.push('Уточните название задачи.');
    if (!value.client_id) missing.push('Уточните клиента.');
    if (!value.assignee_id) missing.push('Уточните исполнителя.');
    if (!value.completion_date) missing.push('Уточните дату выполнения.');
    return missing;
  };

  const createTask = async () => {
    if (text.trim()) {
      await analyze();
      return;
    }
    setQuestions([]);
    setError('');
    setModalDraft(draft);
    return;
    const missing = missingForDraft(draft);
    if (missing.length) {
      setQuestions(missing);
      setError('Не хватает обязательных данных. Уточните их голосом или текстом и нажмите Enter.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const task = await api.createTask({
        title: draft.title || 'Новая задача',
        client_id: draft.client_id || null,
        assignee_id: draft.assignee_id || null,
        task_type: draft.task_type || 'custom',
        priority: draft.priority || 'medium',
        notes: draft.notes || '',
        status: 'todo',
        completion_date: draft.completion_date ? new Date(`${draft.completion_date}T12:00:00`).toISOString() : null,
        deadline: draft.deadline ? new Date(`${draft.deadline}T12:00:00`).toISOString() : null,
      });
      navigate('/tasks');
      setCreatedTask(task);
      setQuestions([]);
      setDraft({});
    } catch (err: any) {
      setError(err instanceof Error ? err.message : 'Не удалось создать задачу.');
    } finally {
      setLoading(false);
    }
  };

  const saveDraftTask = async (data: Partial<Task>) => {
    setLoading(true);
    setError('');
    try {
      const task = await api.createTask({
        ...data,
        title: data.title || draft.title || 'Новая задача',
        status: data.status || 'todo',
      });
      navigate('/tasks');
      setCreatedTask(task);
      setModalDraft(null);
      setQuestions([]);
      setDraft({});
    } catch (err: any) {
      setError(err instanceof Error ? err.message : 'Не удалось создать задачу.');
    } finally {
      setLoading(false);
    }
  };

  const handleEnter = async (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey) return;
    event.preventDefault();
    if (text.trim()) await analyze();
    else if (draft.title) await createTask();
  };

  const saveCreatedTask = async (data: Partial<Task>) => {
    if (!createdTask) return;
    await api.updateTask(createdTask.id, data);
    setCreatedTask(null);
    onClose();
  };

  const summary = [
    ['Задача', draft.title],
    ['Клиент', draft.client_name],
    ['Исполнитель', draft.assignee_name],
    ['Дата выполнения', draft.completion_date],
    ['Дедлайн', draft.deadline],
    ['Приоритет', draft.priority],
    ['Тип', draft.task_type],
  ];

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <section className="fixed right-4 top-20 z-50 w-[min(460px,calc(100vw-32px))] rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <div>
            <h2 className="text-sm font-black">Голосовая задача</h2>
            <p className="text-xs text-[var(--color-text-secondary)]">Скажите команду, затем Enter или OK.</p>
          </div>
          <button type="button" onClick={onClose} className="tf-button w-9 px-0"><X size={15} /></button>
        </div>
        <div className="space-y-3 p-4">
          <textarea
            className="tf-input min-h-28 resize-y"
            value={text}
            onChange={event => setText(event.target.value)}
            onKeyDown={handleEnter}
            placeholder="Например: поставь админу задачу проверить title клиенту Альфа Климат завтра"
            autoFocus
          />
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs leading-5 text-[var(--color-text-secondary)]">
            <div className="mb-1 font-bold text-[var(--color-text)]">Как лучше писать запрос</div>
            <p>Формула: кому поставить, что сделать, для какого клиента, когда выполнить. Описание добавляйте после слова “описание”. Дедлайн называйте отдельно, только если это крайний срок.</p>
            <div className="mt-2 space-y-1">
              <div>Например: “Поставь Ивану задачу проверить title для Альфа Климат завтра”.</div>
              <div>Например: “Создай задачу админу подготовить отчет для клиента Ромашка на 15 июля, дедлайн 18 июля, описание: проверить позиции и добавить ссылки на статьи”.</div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={startListening} className={cn('tf-button', listening && 'text-[var(--color-danger)]')}><Mic size={15} />{listening ? 'Слушаю...' : 'Говорить'}</button>
            <button type="button" onClick={analyze} disabled={loading || !text.trim()} className="tf-button"><Send size={15} />OK</button>
            <button type="button" onClick={createTask} disabled={loading || !draft.title} className="tf-button tf-button-primary">Открыть задачу</button>
          </div>
          {questions.length > 0 && (
            <div className="rounded-lg border border-[var(--color-warning)]/45 bg-[var(--color-warning)]/10 p-3 text-sm">
              <div className="font-bold text-[var(--color-warning)]">Нужно уточнить</div>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-[var(--color-text-secondary)]">
                {questions.map(question => <li key={question}>{question}</li>)}
              </ul>
            </div>
          )}
          {Object.keys(draft).length > 0 && (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-sm">
              <div className="mb-2 font-bold">Черновик</div>
              <div className="grid gap-1">
                {summary.filter(([, value]) => value).map(([label, value]) => (
                  <div key={label} className="grid grid-cols-[130px_1fr] gap-2">
                    <span className="text-[var(--color-muted)]">{label}</span>
                    <span>{String(value)}</span>
                  </div>
                ))}
              </div>
              {draft.notes && <div className="mt-2 text-xs text-[var(--color-text-secondary)]">{draft.notes}</div>}
            </div>
          )}
          {error && <div className="text-sm font-semibold text-[var(--color-danger)]">{error}</div>}
        </div>
      </section>
      {modalDraft && !createdTask && (
        <Suspense fallback={null}>
          <TaskModal task={null} initialTask={modalDraft} clients={clients} users={users} onClose={() => setModalDraft(null)} onSave={saveDraftTask} />
        </Suspense>
      )}
      {createdTask && (
        <Suspense fallback={null}>
          <TaskModal task={createdTask} clients={clients} users={users} onClose={() => { setCreatedTask(null); onClose(); }} onSave={saveCreatedTask} />
        </Suspense>
      )}
    </>
  );
}
