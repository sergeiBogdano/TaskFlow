import { Link } from 'react-router-dom';
import { ArrowUpRight, CheckSquare, NotebookPen, CalendarDays, Columns3, Building2, Timer, LayoutDashboard, Layers, Users, ShieldCheck } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { getActiveWorkspaceDetail } from '../lib/workspace';
import { sectionLabel } from '../lib/uiconfig';
import { availableWorkAreas, WORK_AREAS, type WorkArea } from '../lib/workAreas';
import { SpaceDirectory } from '../components/SpaceDirectory';
import { AiAdminPanel } from '../components/AiAdminPanel';

const tools = [
  { route: '/tasks', permission: 'tasks', icon: CheckSquare, description: 'Разбейте работу или обучение на понятные шаги.' },
  { route: '/notes', permission: 'notes', icon: NotebookPen, description: 'Собирайте идеи, конспекты и знания в папках.' },
  { route: '/calendar', permission: 'calendar', icon: CalendarDays, description: 'Планируйте время и следите за сроками.' },
  { route: '/kanban', permission: 'kanban', icon: Columns3, description: 'Ведите работу от идеи до результата.' },
  { route: '/sprints', permission: 'kanban', icon: Timer, description: 'Выберите цель и задачи на ближайший период.' },
  { route: '/overview', permission: 'dashboard', icon: LayoutDashboard, description: 'Посмотрите прогресс и нагрузку команды.' },
  { route: '/crm', permission: 'crm', icon: Building2, description: 'Клиенты, сделки и отношения с заказчиками.' },
];

export function WorkHome({ area = 'work' }: { area?: WorkArea }) {
  const { user } = useAuth();
  const workspace = getActiveWorkspaceDetail();
  if (!availableWorkAreas(user).includes(area)) return <section className="tf-panel-flat p-6"><h2 className="text-xl font-semibold">Режим недоступен</h2><p className="mt-2">Администратор может проверить ваш профиль доступа.</p><Link className="tf-button mt-4" to="/work">К работе</Link></section>;
  if (area === 'work' && !workspace) return <SpaceDirectory />;
  const visible = tools.filter(item => user?.features?.[item.permission] !== false && (user?.is_root || user?.permissions?.all || user?.permissions?.[item.permission]));
  const cards = area === 'work' ? visible : area === 'manage'
    ? [{ route: '/workspace', icon: Layers, description: 'Основные настройки и оформление пространства.' }, { route: '/access', icon: ShieldCheck, description: 'Единый центр команды, профилей, прав, функций и доступа к полям.' }]
    : [{ route: '/access?scope=app', icon: Users, description: 'Единый центр аккаунтов, профилей приложения, групп и функций.' }];
  return <div className="mx-auto max-w-6xl space-y-8">
    <section className="tf-home-hero rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 sm:p-8">
      <p className="text-xs font-semibold uppercase tracking-widest text-[var(--color-muted)]">{WORK_AREAS[area].title}{area !== 'admin' && workspace?.name ? ` · ${workspace.name}` : ''}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight">{area === 'work' ? 'Место для ваших планов' : area === 'manage' ? 'Понятные правила для команды' : 'Управление приложением'}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--color-text-secondary)]">{area === 'work' ? 'Личный проект, учёба или командная работа: используйте нужные инструменты в выбранном пространстве.' : area === 'manage' ? 'Уровень участника определяет, кем он может управлять. Профиль доступа определяет его действия. Личные исключения уточняют доступ к функциям и полям.' : 'Здесь настраиваются аккаунты и возможности всей системы. Рабочие данные и настройки команды находятся в других режимах.'}</p>
    </section>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{cards.map(item => <Link key={item.route} to={item.route} className="tf-home-tool group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition hover:border-[var(--color-accent)] hover:bg-[var(--color-surface-2)]">
      <div className="flex items-center justify-between"><item.icon size={23} className="tf-home-icon" /><ArrowUpRight size={17} className="text-[var(--color-muted)]" /></div>
      <h3 className="mt-4 font-semibold">{sectionLabel(item.route.split('?')[0])}</h3><p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{item.description}</p>
    </Link>)}</div>
    {area === 'work' && !visible.length && <p className="tf-panel-flat p-5">В этом пространстве пока нет доступных инструментов. Попросите администратора проверить модули и ваш профиль.</p>}

    {area === 'admin' && user?.is_root && <AiAdminPanel />}
    <div className="flex flex-wrap gap-3 text-sm"><Link className="tf-button" to="/settings">Личные настройки</Link><Link className="tf-button" to="/wiki">Руководство</Link></div>
  </div>;
}
