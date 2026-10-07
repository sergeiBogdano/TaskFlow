import type { User } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import { UserMultiSelect } from './UserMultiSelect';
import type { TaskScope } from '../lib/taskScope';

type Props = {
  users: User[];
  scope: TaskScope;
  userId: string;
  onScopeChange: (scope: TaskScope) => void;
  onUserChange: (userId: string) => void;
  className?: string;
};

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

  return (
    <div className={`rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-1.5 ${className}`} style={{ boxShadow: 'var(--shadow-soft)' }}>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(180px,1.25fr)]">
        <div style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }} className="grid gap-1.5 rounded-full bg-[var(--color-overlay)] p-1.5">
          {options.map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => onScopeChange(option.value)}
              className={`h-9 whitespace-nowrap rounded-full px-3 text-[13px] font-semibold transition active:scale-[.97] ${normalizedScope === option.value ? 'bg-[var(--color-accent)] text-[var(--color-on-accent)] shadow-[var(--shadow-accent)]' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-overlay)] hover:text-[var(--color-text)]'}`}
            >
              {option.label}
            </button>
          ))}
        </div>
      {normalizedScope === 'user' ? (
        <UserMultiSelect users={users} selected={selectedUserIds} onChange={ids => onUserChange(ids.join(','))} />
      ) : (
        <div className="hidden sm:block rounded-md bg-black/[.06]" />
      )}
      </div>
    </div>
  );
}
