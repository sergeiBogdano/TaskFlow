import { Link, Navigate, Outlet } from 'react-router-dom';
import { PasswordChange } from './PasswordChange';
import { useAuth } from '../hooks/useAuth';
import { getActiveWorkspaceId } from '../lib/workspace';
import { SpaceDirectory } from './SpaceDirectory';

export function PrivateRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-[var(--color-text-secondary)]">Загрузка...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <div className="grid min-h-screen place-items-center p-4"><PasswordChange required /></div>;
  return <Outlet />;
}

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-[var(--color-text-secondary)]">Загрузка...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_root && !user.permissions?.users && !user.permissions?.users_manage) return <AccessUnavailable />;
  return <>{children}</>;
}

export function PermissionRoute({ permission, children }: { permission: string; children: React.ReactNode }) {
  const { user, loading, hasRole } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-[var(--color-text-secondary)]">Загрузка...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.is_root && !['crm', 'clients', 'tasks', 'kanban', 'calendar', 'notes', 'reports', 'modules', 'ai'].includes(permission)) return <>{children}</>;
  if (user.features && user.features[permission] === false) return <AccessUnavailable disabled />;
  if (!user.is_root && !hasRole('superadmin') && !user.permissions?.all && !user.permissions?.[permission]) {
    return <AccessUnavailable />;
  }
  return <>{children}</>;
}

function AccessUnavailable({ disabled = false }: { disabled?: boolean }) {
  if (!getActiveWorkspaceId()) return <SpaceDirectory />;
  return <section className="tf-panel-flat mx-auto max-w-xl space-y-4 p-6" role="status">
    <h2 className="text-xl font-bold">Раздел недоступен</h2>
    <p className="text-sm leading-6 text-[var(--color-text-secondary)]">{disabled
      ? 'Функция отключена для вашего аккаунта или текущего пространства. Обратитесь к суперадмину.'
      : 'Проверьте выбранное пространство. Попросите его владельца проверить ваше членство и профиль доступа.'}</p>
    <div className="flex flex-wrap gap-2"><Link className="tf-button tf-button-primary" to="/wiki?article=troubleshooting">Как проверить доступ</Link>
      <Link className="tf-button" to="/settings">Личные настройки</Link></div>
  </section>;
}
