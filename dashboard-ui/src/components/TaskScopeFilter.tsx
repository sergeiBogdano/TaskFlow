import type { Task, User } from '../api/client';
import { useAuth } from '../hooks/useAuth';

export type TaskScope = 'mine' | 'assigned' | 'coassigned' | 'created' | 'involved' | 'user' | 'all';

type Props = {
  users: User[];
  scope: TaskScope;
  userId: string;
  onScopeChange: (scope: TaskScope) => void;
  onUserChange: (userId: string) => void;
  className?: string;
};

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

export function TaskScopeFilter({ users, scope, userId, onScopeChange, onUserChange, className = '' }: Props) {
  const { user, hasRole } = useAuth();
  const permissions = user?.permissions || {};
  const canViewAll = hasRole('superadmin') || Boolean(permissions.all || permissions.tasks_view_all || permissions.tasks_view_others);
  const canViewTeam = canViewAll || Boolean(permissions.tasks_view_team);

  const options: { value: TaskScope; label: string }[] = [
    { value: 'mine', label: 'Мои' },
  ];
  if (canViewTeam) options.push({ value: 'user', label: 'Сотрудник' });
  if (canViewAll) options.push({ value: 'all', label: 'Все' });

  const normalizedScope = options.some(item => item.value === scope) ? scope : 'mine';
  const selectedUserIds = userId.split(',').map(item => Number(item)).filter(Boolean);
  const toggleUser = (nextUserId: number) => {
    const next = selectedUserIds.includes(nextUserId)
      ? selectedUserIds.filter(item => item !== nextUserId)
      : [...selectedUserIds, nextUserId];
    onUserChange(next.join(','));
  };

  return (
    <div className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-1 ${className}`}>
      <div className="grid grid-cols-1 gap-1 sm:grid-cols-[minmax(0,1fr)_minmax(180px,1.25fr)]">
        <div className="grid grid-cols-3 gap-1">
          {options.map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => onScopeChange(option.value)}
              className={`h-8 rounded-md px-2 text-xs font-bold ${normalizedScope === option.value ? 'bg-[var(--color-accent)] text-white' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)] hover:text-white'}`}
            >
              {option.label}
            </button>
          ))}
        </div>
      {normalizedScope === 'user' ? (
        <details className="relative">
          <summary className="tf-input flex min-h-[38px] list-none items-center justify-between gap-2 text-left text-sm">
            <span className={selectedUserIds.length ? 'truncate' : 'truncate text-[var(--color-muted)]'}>
              {selectedUserIds.length ? `Выбрано: ${selectedUserIds.length}` : 'Выберите сотрудников'}
            </span>
            <span className="text-xs text-[var(--color-muted)]">▼</span>
          </summary>
          <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-[90] max-h-72 overflow-auto rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-surface)] p-2 shadow-2xl">
            <div className="mb-2 flex gap-2">
              <button type="button" className="tf-button h-7 px-2 text-xs" onClick={() => onUserChange(users.map(item => item.id).join(','))}>Все</button>
              <button type="button" className="tf-button h-7 px-2 text-xs" onClick={() => onUserChange('')}>Снять</button>
            </div>
            <div className="space-y-1">
              {users.map(item => (
                <label key={item.id} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-[var(--color-surface-2)]">
                  <input type="checkbox" checked={selectedUserIds.includes(item.id)} onChange={() => toggleUser(item.id)} className="accent-[var(--color-accent)]" />
                  <span className="truncate">{item.username}</span>
                </label>
              ))}
            </div>
          </div>
        </details>
      ) : (
        <div className="hidden sm:block rounded-md bg-black/10" />
      )}
      </div>
    </div>
  );
}
