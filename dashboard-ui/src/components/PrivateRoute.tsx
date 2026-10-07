import { Navigate, Outlet } from 'react-router-dom';
import { PasswordChange } from './PasswordChange';
import { useAuth } from '../hooks/useAuth';

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
  if (!user.is_root && !user.permissions?.users && !user.permissions?.users_manage) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function PermissionRoute({ permission, children }: { permission: string; children: React.ReactNode }) {
  const { user, loading, hasRole } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-[var(--color-text-secondary)]">Загрузка...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.is_root && !['crm', 'clients', 'tasks', 'kanban', 'calendar', 'notes', 'reports', 'modules', 'ai'].includes(permission)) return <>{children}</>;
  if (user.features && user.features[permission] === false) return <Navigate to="/" replace />;
  if (!user.is_root && !hasRole('superadmin') && !user.permissions?.all && !user.permissions?.[permission]) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
