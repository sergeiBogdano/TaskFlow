import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export function PrivateRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-[var(--color-text-secondary)]">Загрузка...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, hasRole } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-[var(--color-text-secondary)]">Загрузка...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (!hasRole('superadmin') && !hasRole('admin')) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function PermissionRoute({ permission, children }: { permission: string; children: React.ReactNode }) {
  const { user, loading, hasRole } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-[var(--color-text-secondary)]">Загрузка...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (!hasRole('superadmin') && !user.permissions?.all && !user.permissions?.[permission]) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
