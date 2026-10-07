import type { Task, User } from '../api/client';

export type TaskScope = 'mine' | 'assigned' | 'coassigned' | 'created' | 'involved' | 'user' | 'all';

export function taskMatchesScope(task: Task, currentUser: User | null | undefined, scope: TaskScope, scopeUserId = '') {
  if (!currentUser?.id) return false;
  const permissions = currentUser.permissions || {};
  const isSuperadmin = currentUser.roles?.some(role => role.name === 'superadmin');
  const canViewAll = Boolean(isSuperadmin || permissions.all || permissions.tasks_view_all || permissions.tasks_view_others);
  const canViewTeam = Boolean(canViewAll || permissions.tasks_view_team);
  const currentUserId = currentUser.id;
  const selectedUserIds = scope === 'user' && scopeUserId && canViewTeam
    ? scopeUserId.split(',').map(item => Number(item)).filter(Boolean)
    : [];
  const targetUserIds = selectedUserIds.length ? selectedUserIds : [currentUserId];
  const coExecutorIds = new Set([task.co_executor_id, ...(task.co_executor_ids || [])].filter(Boolean).map(Number));
  if (scope === 'all') return canViewAll ? true : Number(task.assignee_id) === currentUserId;
  const matchesAny = (checker: (userId: number) => boolean) => targetUserIds.some(checker);
  if (scope === 'mine' || scope === 'assigned') return matchesAny(userId => Number(task.assignee_id) === userId);
  if (scope === 'coassigned') return matchesAny(userId => coExecutorIds.has(userId));
  if (scope === 'created') return matchesAny(userId => Number(task.creator_id) === userId);
  if (scope === 'user' || scope === 'involved') {
    return matchesAny(userId => Number(task.assignee_id) === userId || Number(task.creator_id) === userId || coExecutorIds.has(userId));
  }
  return Number(task.assignee_id) === currentUserId;
}
