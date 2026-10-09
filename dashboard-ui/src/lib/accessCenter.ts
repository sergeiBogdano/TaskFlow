export type AccessScope = 'space' | 'app';
export type AccessTab = { id: string; label: string; hint: string };
type Account = { is_root?: boolean; permissions?: Record<string, boolean>; features?: Record<string, boolean> } | null;
export function accessSections(user: Account, rank?: string) {
  const root = Boolean(user?.is_root);
  const allowed = (key: string) => root || Boolean(user?.permissions?.[key] && user?.features?.[key] !== false);
  const managesSpace = root || rank === 'owner' || rank === 'admin';
  const space: AccessTab[] = [];
  if (managesSpace && allowed('workspace_profiles')) space.push(
    { id: 'members', label: 'Доступ участников', hint: 'Выберите человека: профиль, права, функции и поля.' },
    { id: 'profiles', label: 'Рабочие профили', hint: 'Настройте общий набор прав для работы в этом пространстве.' });
  if (managesSpace && allowed('workspace_members')) space.push({ id: 'team', label: 'Состав команды', hint: 'Приглашения и уровни управления участниками.' });
  if (root) space.push({ id: 'tools', label: 'Модули и функции', hint: 'Какие инструменты доступны в выбранном пространстве.' });
  const app: AccessTab[] = [];
  if (allowed('users') || allowed('users_manage')) app.push({ id: 'users', label: 'Аккаунты', hint: 'Создание аккаунтов, блокировка и профили приложения.' });
  if (root) app.push(
    { id: 'roles', label: 'Профили приложения', hint: 'Права на управление аккаунтами и приложением.' },
    { id: 'groups', label: 'Группы', hint: 'Участники группы, общие права и ограничения функций.' },
    { id: 'features', label: 'Функции приложения', hint: 'Общие запреты и разрешения для всего приложения.' });
  return { space, app };
}
export function resolveAccessSelection(sections: ReturnType<typeof accessSections>, scope?: string | null, tab?: string | null) {
  const selectedScope: AccessScope = scope === 'app' && sections.app.length ? 'app' : scope === 'space' && sections.space.length ? 'space' : sections.space.length ? 'space' : 'app';
  const selectedTab = sections[selectedScope].find(item => item.id === tab) || sections[selectedScope][0];
  return { scope: selectedScope, tab: selectedTab };
}
