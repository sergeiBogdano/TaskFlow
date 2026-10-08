export type WorkArea = 'work' | 'manage' | 'admin';
type Account = { is_root?: boolean; permissions?: Record<string, boolean> } | null;

export function workAreaForRoute(route: string): WorkArea {
  if (['/admin', '/users'].some(path => route === path || route.startsWith(path + '/'))) return 'admin';
  if (['/manage', '/workspace'].some(path => route === path || route.startsWith(path + '/'))) return 'manage';
  return 'work';
}

export function availableWorkAreas(user: Account): WorkArea[] {
  if (!user) return [];
  const permissions = user.permissions || {};
  const areas: WorkArea[] = ['work'];
  if (user.is_root || permissions.all || ['workspace_settings', 'workspace_members', 'workspace_profiles', 'workspaces_create'].some(key => permissions[key])) areas.push('manage');
  if (user.is_root || permissions.all || permissions.users || permissions.users_manage) areas.push('admin');
  return areas;
}

export const WORK_AREAS = {
  work: { title: 'Работа', route: '/work', hint: 'Задачи, знания и планы' },
  manage: { title: 'Управление', route: '/manage', hint: 'Команда и пространство' },
  admin: { title: 'Администрирование', route: '/admin', hint: 'Пользователи и возможности системы' },
};
