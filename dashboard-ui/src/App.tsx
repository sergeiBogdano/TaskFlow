import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth';
import { AdminRoute, PermissionRoute, PrivateRoute } from './components/PrivateRoute';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';

const Dashboard = lazy(() => import('./pages/Dashboard').then(module => ({ default: module.Dashboard })));
const Tasks = lazy(() => import('./pages/Tasks').then(module => ({ default: module.Tasks })));
const Kanban = lazy(() => import('./pages/Kanban').then(module => ({ default: module.Kanban })));
const Clients = lazy(() => import('./pages/Clients').then(module => ({ default: module.Clients })));
const Reports = lazy(() => import('./pages/Reports').then(module => ({ default: module.Reports })));
const Calendar = lazy(() => import('./pages/Calendar').then(module => ({ default: module.Calendar })));
const Notifications = lazy(() => import('./pages/Notifications').then(module => ({ default: module.Notifications })));
const Users = lazy(() => import('./pages/Users').then(module => ({ default: module.Users })));
const Settings = lazy(() => import('./pages/Settings').then(module => ({ default: module.Settings })));
const Modules = lazy(() => import('./pages/Modules').then(module => ({ default: module.Modules })));
const Trash = lazy(() => import('./pages/Trash').then(module => ({ default: module.Trash })));

function PageLoader() {
  return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка раздела...</div>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<PrivateRoute />}>
              <Route element={<Layout />}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/tasks" element={<PermissionRoute permission="tasks"><Tasks /></PermissionRoute>} />
                <Route path="/kanban" element={<PermissionRoute permission="kanban"><Kanban /></PermissionRoute>} />
                <Route path="/clients" element={<PermissionRoute permission="clients"><Clients /></PermissionRoute>} />
                <Route path="/clients/:id" element={<PermissionRoute permission="clients"><Clients /></PermissionRoute>} />
                <Route path="/modules" element={<PermissionRoute permission="modules"><Modules /></PermissionRoute>} />
                <Route path="/calendar" element={<PermissionRoute permission="calendar"><Calendar /></PermissionRoute>} />
                <Route path="/notifications" element={<PermissionRoute permission="notifications"><Notifications /></PermissionRoute>} />
                <Route path="/users" element={<AdminRoute><Users /></AdminRoute>} />
                <Route path="/reports" element={<PermissionRoute permission="reports"><Reports /></PermissionRoute>} />
                <Route path="/trash" element={<PermissionRoute permission="tasks"><Trash /></PermissionRoute>} />
                <Route path="/settings" element={<PermissionRoute permission="settings"><Settings /></PermissionRoute>} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}
