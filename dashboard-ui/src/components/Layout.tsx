import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { DndContext, DragOverlay, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, arrayMove, rectSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  BarChart3,
  Building2,
  BookOpen,
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
  Layers,
  NotebookPen,
  Puzzle,
  Settings,
  Sparkles,
  Timer,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { api } from '../api/client';
import { WorkspaceSwitcher } from './WorkspaceSwitcher';
import { accessSections } from '../lib/accessCenter';
import { availableWorkAreas, workAreaForRoute, WORK_AREAS } from '../lib/workAreas';
import { WORKSPACE_EVENT, getActiveWorkspaceDetail } from '../lib/workspace';
import { isNavVisible, navOverride, sectionLabel } from '../lib/uiconfig';
import { useAuth } from '../hooks/useAuth';
import { cn, roleMeta } from '../lib/taskflow';


const nav = [
  {
    section: 'Помощь',
    items: [{ to: '/wiki', icon: BookOpen, label: 'Вики', hint: 'Как всё устроено', permission: 'wiki' }],
  },
  {
    section: 'Работа',
    items: [
      { to: '/overview', icon: LayoutDashboard, label: 'Дашборд', hint: 'Обзор команды', permission: 'dashboard' },
      { to: '/tasks', icon: CheckSquare, label: 'Задачи', hint: 'Список и фильтры', permission: 'tasks' },
      { to: '/sprints', icon: Timer, label: 'Спринты', hint: 'Отрезки и прогресс', permission: 'kanban' },
      { to: '/kanban', icon: Columns3, label: 'Канбан', hint: 'Поток работы', permission: 'kanban' },
      { to: '/calendar', icon: CalendarDays, label: 'Календарь', hint: 'План выполнения', permission: 'calendar' },
      { to: '/notifications', icon: Bell, label: 'Уведомления', hint: 'События', permission: 'notifications' },
      { to: '/notes', icon: NotebookPen, label: 'Заметки', hint: 'Идеи и черновики', permission: 'notes' },
      { to: '/trash', icon: Trash2, label: 'Корзина', hint: 'Удалённые задачи', permission: 'tasks' },
    ],
  },
  {
    section: 'Дополнительно',
    items: [
      { to: '/crm', icon: Building2, label: 'CRM', hint: 'Сделки и контакты', permission: 'crm' },
      { to: '/clients', icon: Users, label: 'Клиенты', hint: 'CRM и договоры', permission: 'clients' },
      { to: '/modules', icon: Puzzle, label: 'Модули', hint: 'Автоматизация', permission: 'modules' },
      { to: '/reports', icon: BarChart3, label: 'Отчёты', hint: 'Метрики', permission: 'reports' },
      { to: '/ai', icon: Sparkles, label: 'Помощник', hint: 'Диалог и черновики', permission: 'ai' },
    ],
  },
  {
    section: 'Система',
    items: [
      { to: '/access', icon: CircleUser, label: 'Права и доступ', hint: 'Пользователи, роли и функции', permission: 'access_center' },
      { to: '/workspace', icon: Layers, label: 'Окружение', hint: 'Настройки и команда', permission: 'workspace' },
      { to: '/settings', icon: Settings, label: 'Настройки', hint: 'Профиль', permission: 'settings' },
    ],
  },
];



type NavItem = typeof nav[number]['items'][number];

function SortableNavItem({ item, unreadCount, compact }: { item: NavItem; unreadCount: number; compact: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.to });
  return (
    <NavLink
      ref={setNodeRef}
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) => cn(
        'group flex min-w-[74px] flex-col items-center justify-center gap-1 rounded-xl px-2 py-2 text-center text-xs lg:min-w-0 lg:flex-row lg:justify-start lg:gap-3 lg:px-3 lg:py-2.5 lg:text-left lg:text-sm',
        compact && 'lg:justify-center lg:px-2',
        !isActive && 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text)]',
      )}
      style={({ isActive }) => ({
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.35 : 1,
        ...(isActive
          ? { background: 'var(--color-accent)', color: 'var(--color-on-accent)', boxShadow: '0 8px 20px rgba(43,38,32,.3)' }
          : undefined),
      })}
    >
      {({ isActive: active }) => (
        <>
          <item.icon size={19} />
          <span className={cn('min-w-0 lg:flex-1', compact && 'lg:hidden')}>
            <span className="block truncate font-medium">{item.label}</span>
            <span
              className="hidden truncate text-[11px] lg:block"
              style={{ color: active ? 'rgba(245,241,234,.68)' : 'var(--color-muted)' }}
            >
              {item.hint}
            </span>
          </span>
          {item.to === '/notifications' && unreadCount > 0 && <span className="rounded-full bg-[var(--color-danger)] px-1.5 py-0.5 text-[10px] font-bold text-white">{unreadCount > 99 ? '99+' : unreadCount}</span>}
          <button
            type="button"
            {...attributes}
            {...listeners}
            onClick={event => { event.preventDefault(); event.stopPropagation(); }}
            className={cn('grid h-7 w-7 shrink-0 place-items-center rounded-md opacity-70 lg:opacity-0 lg:group-hover:opacity-100', compact && 'lg:hidden', !active && 'text-[var(--color-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]')}
            style={active ? { color: 'rgba(245,241,234,.65)' } : undefined}
            aria-label={`Перетащить ${item.label}`}
            title={`Перетащить ${item.label}`}
          >
            <GripVertical size={14} />
          </button>
        </>
      )}
    </NavLink>
  );
}

export function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, hasRole } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);
  const [showIntro, setShowIntro] = useState(() => localStorage.getItem('taskflow:intro-closed') !== '1');
  const [navOrder, setNavOrder] = useState<Record<string, string[]>>({});
  const [activeNavRoute, setActiveNavRoute] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('taskflow:sidebar-collapsed') === '1');
  const [, setUiTick] = useState(0);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const notificationsAvailable = Boolean(user?.is_root || (user?.features?.notifications !== false && (user?.permissions?.all || user?.permissions?.notifications)));
  const voiceAvailable = ['ai'].every(key => user?.features?.[key] !== false && (user?.is_root || user?.permissions?.all || user?.permissions?.[key]));

  useEffect(() => {
    const sync = () => {
      setUiTick(tick => tick + 1);
    };
    window.addEventListener(WORKSPACE_EVENT, sync);
    return () => window.removeEventListener(WORKSPACE_EVENT, sync);
  }, []);

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
    if (!notificationsAvailable) { setUnreadCount(0); return; }
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
  }, [notificationsAvailable]);

  const primaryRole = user?.roles?.[0]?.name || 'executor';
  const role = roleMeta[primaryRole] || roleMeta.executor;
  const isSuperadmin = hasRole('superadmin');
  const canSee = (permission: string) => {
    if (permission === 'access_center') { const sections = accessSections(user, getActiveWorkspaceDetail()?.role); return !!(sections.space.length || sections.app.length); }
    if (permission === 'wiki') return true;
    if (permission === 'settings') return true;
    if (permission === 'workspace') return true;
    if (permission === 'users') return Boolean(user?.is_root || user?.permissions?.all || user?.permissions?.users || user?.permissions?.users_manage);
    if (user?.is_root && !['crm', 'clients', 'tasks', 'kanban', 'calendar', 'notes', 'reports', 'modules', 'ai'].includes(permission)) return true;
    // кран доступности (Ф6) действует и на суперадмина: функция выключена — пункта нет
    if (user?.features && user.features[permission] === false) return false;
    if (isSuperadmin) return true;
    return Boolean(user?.permissions?.all || user?.permissions?.[permission]);
  };
  const areas = availableWorkAreas(user);
  const area = location.pathname === '/access' && (new URLSearchParams(location.search).get('scope') === 'app' || !areas.includes('manage')) ? 'admin' : workAreaForRoute(location.pathname);
  const pageTitle = sectionLabel(location.pathname === '/' ? '/work' : location.pathname);

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
    const saved = navOrder[section] || (section === 'Дополнительно' ? navOrder['Клиенты'] : undefined) || [];
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
        <div className="mb-2 flex shrink-0 items-center gap-3 px-2 py-2 lg:mb-4">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-accent)] text-sm font-black text-[var(--color-on-accent)]">TF</div>
          <div className={cn('min-w-0', sidebarCollapsed && 'lg:hidden')}>
            <div className="text-sm font-bold tracking-wide">TaskFlow</div>
            <div className="text-xs text-[var(--color-text-secondary)]">Рабочие пространства</div>
          </div>
          <button type="button" onClick={toggleSidebar} className={cn('tf-button ml-auto hidden w-9 px-0 lg:inline-flex', sidebarCollapsed && 'lg:ml-0')} title={sidebarCollapsed ? 'Показать меню' : 'Скрыть меню'} aria-label={sidebarCollapsed ? 'Показать меню' : 'Скрыть меню'}>
            {sidebarCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        </div>

        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={event => setActiveNavRoute(String(event.active.id))} onDragCancel={() => setActiveNavRoute(null)} onDragEnd={handleNavDragEnd}>
        <div className={cn(sidebarCollapsed && 'lg:hidden')}>
          <WorkspaceSwitcher compact={sidebarCollapsed} />
        </div>
        <div className="my-3 flex shrink-0 gap-1 overflow-x-auto rounded-lg bg-[var(--color-surface-2)] p-1 lg:flex-col" aria-label="Режим приложения">{areas.map(key => <NavLink key={key} to={WORK_AREAS[key].route} title={WORK_AREAS[key].hint} className={cn('rounded-md px-3 py-2 text-xs font-semibold transition', area === key ? 'bg-[var(--color-surface)] text-[var(--color-text)] shadow-sm' : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text)]')}>{sidebarCollapsed ? WORK_AREAS[key].title.slice(0, 1) : WORK_AREAS[key].title}</NavLink>)}</div>
        <NavLink to={WORK_AREAS[area].route} className="tf-button mb-3 w-full shrink-0">{sidebarCollapsed ? '⌂' : area === 'work' ? 'Мой рабочий стол' : 'Обзор режима'}</NavLink>
        <nav className={cn('flex shrink-0 gap-2 overflow-x-auto pb-1 lg:block lg:overflow-visible lg:pb-0', sidebarCollapsed ? 'lg:space-y-2' : 'lg:space-y-4')}>
          {nav.map(group => {
            const visibleItems = group.items.filter(item => (item.to === '/access' ? area === 'manage' || area === 'admin' : workAreaForRoute(item.to) === area) && item.to !== '/settings' && canSee(item.permission));
            if (!visibleItems.length) return null;
            const shownItems = orderedItems(group.section, visibleItems)
              .filter(item => item.to === '/wiki' || isNavVisible(item.to))
              .map(item => {
                const override = navOverride(item.to);
                const label = sectionLabel(item.to);
                const hint = override?.hint?.trim() || item.hint;
                return { ...item, label, hint };
              });
            if (!shownItems.length) return null;
            return (
              <div key={group.section} className={cn('flex shrink-0 gap-2 lg:block', sidebarCollapsed && 'lg:flex lg:justify-center')}>
                <div className={cn('hidden px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--color-muted)] lg:block', sidebarCollapsed && 'lg:hidden')}>{group.section}</div>
                <SortableContext items={shownItems.map(item => item.to)} strategy={rectSortingStrategy}>
                  <div className={cn('flex gap-2 lg:block lg:space-y-1', sidebarCollapsed && 'lg:w-full')}>
                    {shownItems.map(item => (
                      <SortableNavItem
                        key={item.to}
                        item={item}
                        unreadCount={unreadCount}
                        compact={sidebarCollapsed}
                      />
                    ))}
                  </div>
                </SortableContext>
              </div>
            );
          })}
        </nav>
        <DragOverlay>{activeNavRoute ? <div className="rounded-lg border border-[var(--color-accent)] bg-[var(--color-surface-3)] px-3 py-2 text-sm font-semibold text-[var(--color-text)] shadow-xl">{sectionLabel(activeNavRoute)}</div> : null}</DragOverlay>
        </DndContext>

        <div className={cn('mt-auto hidden shrink-0 space-y-3 lg:block', sidebarCollapsed && 'lg:hidden')}>
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
          <NavLink to="/settings" className="tf-button w-full justify-start"><Settings size={16} />Личные настройки</NavLink>
          <button onClick={handleLogout} className="tf-button w-full justify-start text-[var(--color-text-secondary)] hover:text-[var(--color-danger)]">
            <LogOut size={16} />
            Выйти
          </button>
        </div>
      </aside>

      <div className={cn(sidebarCollapsed ? 'lg:pl-[76px]' : 'lg:pl-[264px]')}>
        <header className="sticky top-0 z-20 flex min-h-16 items-center gap-4 border-b border-[var(--color-border)] bg-[var(--color-header)] px-4 py-3 sm:px-8">
          <div className="min-w-0">
            <h1 className="text-[17px] font-semibold tracking-tight">{pageTitle}</h1>
            <p className="text-xs text-[var(--color-text-secondary)]">{WORK_AREAS[area].hint}</p>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-2">
          {area === 'work' && voiceAvailable && <button onClick={() => navigate('/ai')} className="tf-button w-10 px-0 text-[var(--color-accent)]" aria-label="Помощник">
            <Mic size={16} />
          </button>}
          {notificationsAvailable && <button onClick={() => navigate('/notifications')} className="tf-button relative w-10 px-0" aria-label="Уведомления">
            <Bell size={16} />
            {unreadCount > 0 && <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-[var(--color-danger)]" />}
          </button>}
          <button onClick={handleLogout} className="tf-button w-10 px-0 lg:hidden" aria-label="Выйти">
            <LogOut size={16} />
          </button>
          </div>
        </header>

        <main className="min-h-[calc(100vh-64px)] p-4 sm:p-8">
          {showIntro && area === 'work' && (
            <section className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <h2 className="text-sm font-bold">Коротко о работе в TaskFlow</h2>
                  <p className="mt-1 text-sm text-[var(--color-text-secondary)]">
                    Выберите пространство команды. Его участники, права и включённые модули определяют доступные разделы. Дедлайн задачи задаёт крайний срок.
                  </p>
                </div>
                <button type="button" onClick={closeIntro} className="grid h-8 w-8 place-items-center rounded-md border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)]" aria-label="Закрыть">
                  <X size={15} />
                </button>
              </div>
            </section>
          )}
          <div key={location.pathname} className="anim-page">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
