import { useEffect, useState, type FormEvent } from 'react';
import { Building2, LayoutDashboard, ListChecks, Lock, Plus, Save, Search, Settings2, ShieldCheck, Trash2, UsersRound, X } from 'lucide-react';
import { api } from '../api/client';
import type { Role, User } from '../api/client';
import { useAuth } from '../hooks/useAuth';

type PermissionItem = { key: string; label: string; hint: string; level?: 'basic' | 'advanced' | 'sensitive' };
type PermissionGroup = { id: string; title: string; icon: any; description: string; items: PermissionItem[] };

const permissionGroups: PermissionGroup[] = [
  {
    id: 'navigation',
    icon: LayoutDashboard,
    description: 'Какие основные разделы будут видны пользователю в меню.',
    title: 'Разделы приложения',
    items: [
      { key: 'dashboard', label: 'Дашборд', hint: 'Главная сводка и здоровье организаций', level: 'basic' },
      { key: 'tasks', label: 'Задачи', hint: 'Список задач и создание задач', level: 'basic' },
      { key: 'kanban', label: 'Канбан', hint: 'Доска статусов и перетаскивание задач', level: 'basic' },
      { key: 'calendar', label: 'Календарь', hint: 'Задачи по дате выполнения', level: 'basic' },
      { key: 'clients', label: 'Клиенты', hint: 'Карточки организаций и справочник клиентов', level: 'basic' },
      { key: 'modules', label: 'Модули', hint: 'Автоматическое создание задач по расписанию', level: 'advanced' },
      { key: 'reports', label: 'Отчёты и аналитика', hint: 'Отчеты, клиентская аналитика и выгрузки', level: 'advanced' },
      { key: 'notifications', label: 'Уведомления', hint: 'Личные и системные уведомления', level: 'basic' },
    ],
  },
  {
    id: 'tasks',
    icon: ListChecks,
    title: 'Работа',
    description: 'Кто какие задачи видит и может выбирать в фильтрах.',
    items: [
      { key: 'tasks_view_team', label: 'Выбор сотрудника', hint: 'Можно смотреть задачи выбранного сотрудника в фильтрах', level: 'advanced' },
      { key: 'tasks_view_others', label: 'Видеть чужие задачи', hint: 'Доступ к задачам других сотрудников в рамках разрешенных клиентов', level: 'sensitive' },
      { key: 'tasks_view_all', label: 'Видеть все задачи', hint: 'Максимальный обзор задач команды', level: 'sensitive' },
      { key: 'dashboard_team', label: 'Командный дашборд', hint: 'Сводки и здоровье организаций по команде, а не только по себе', level: 'advanced' },
    ],
  },
  {
    id: 'clients',
    icon: Building2,
    title: 'Клиенты и отчёты',
    description: 'Доступ к вкладкам клиента. Название организации доступно всем с правом “Клиенты”, а чувствительные вкладки настраиваются отдельно.',
    items: [
      { key: 'client_tab_contacts', label: 'Контакты', hint: 'Контактные лица клиента', level: 'basic' },
      { key: 'client_tab_access', label: 'Доступы', hint: 'Логины, пароли, URL и доступ пользователей к клиенту', level: 'sensitive' },
      { key: 'client_tab_contracts', label: 'Договоры', hint: 'Сроки, продления и файлы договоров', level: 'sensitive' },
      { key: 'client_tab_notes', label: 'Заметки', hint: 'Конкуренты и внутренние заметки клиента', level: 'sensitive' },
      { key: 'client_tab_related', label: 'Задачи и модули', hint: 'Связанные задачи и подключенные модули клиента', level: 'advanced' },
      { key: 'client_tab_activity', label: 'История', hint: 'Журнал изменений клиента', level: 'advanced' },
      { key: 'client_delete', label: 'Удаление клиентов', hint: 'Перемещение клиентов в корзину и массовое удаление', level: 'sensitive' },
    ],
  },
  {
    id: 'system',
    icon: Settings2,
    title: 'Система',
    description: 'Администрирование приложения. Эти права лучше выдавать редко.',
    items: [
      { key: 'users', label: 'Пользователи и роли', hint: 'Создание пользователей, назначение ролей, настройка прав', level: 'sensitive' },
      { key: 'settings', label: 'Настройки', hint: 'Системные настройки приложения', level: 'sensitive' },
    ],
  },
];

const rolePresets = {
  executor: ['dashboard', 'tasks', 'kanban', 'calendar', 'clients', 'notifications'],
  manager: ['dashboard', 'dashboard_team', 'tasks', 'tasks_view_team', 'kanban', 'calendar', 'clients', 'client_tab_contacts', 'client_tab_contracts', 'client_tab_related', 'client_tab_activity', 'modules', 'reports', 'notifications'],
  admin: ['dashboard', 'dashboard_team', 'tasks', 'tasks_view_team', 'tasks_view_others', 'kanban', 'calendar', 'clients', 'client_tab_contacts', 'client_tab_access', 'client_tab_contracts', 'client_tab_notes', 'client_tab_related', 'client_tab_activity', 'client_delete', 'modules', 'reports', 'notifications', 'settings'],
} as const;

export function Users() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newRoleName, setNewRoleName] = useState('');
  const [roleName, setRoleName] = useState('');
  const [permissionSearch, setPermissionSearch] = useState('');

  const load = async () => {
    const [userList, roleList] = await Promise.all([api.getUsers(), api.getRoles()]);
    setUsers(userList);
    setRoles(roleList);
    const firstEditable = roleList.find(role => role.name !== 'superadmin');
    if (!selectedRoleId && firstEditable) {
      setSelectedRoleId(firstEditable.id);
      setPermissions(firstEditable.permissions || {});
    }
  };

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, []);

  const selectRole = (roleId: number) => {
    const role = roles.find(item => item.id === roleId);
    setSelectedRoleId(roleId);
    setPermissions(role?.permissions || {});
    setRoleName(role?.name || '');
  };

  const handleDelete = async (target: User) => {
    if (isProtectedSuperadmin(target, users)) return;
    if (!confirm(`Удалить пользователя ${target.username}?`)) return;
    await api.deleteUser(target.id);
    setUsers(prev => prev.filter(user => user.id !== target.id));
  };

  const handleSetRole = async (userId: number, roleId: number) => {
    if (!roleId) return;
    await api.setUserRole(userId, roleId);
    await load();
  };

  const saveRolePermissions = async () => {
    if (!selectedRoleId) return;
    const role = roles.find(item => item.id === selectedRoleId);
    if (!role || role.name === 'superadmin') return;
    await api.updateRole(role.id, { name: roleName.trim() || role.name, permissions });
    await load();
  };

  const handleCreate = async (username: string, password: string) => {
    await api.createUser(username, password);
    setShowModal(false);
    await load();
  };

  const createRole = async () => {
    const name = newRoleName.trim();
    if (!name) return;
    const role = await api.createRole({ name, permissions: { dashboard: true, tasks: true, notifications: true } });
    setNewRoleName('');
    await load();
    setSelectedRoleId(role.id);
    setPermissions(role.permissions || {});
    setRoleName(role.name);
  };

  const applyPreset = (preset: keyof typeof rolePresets) => {
    const next: Record<string, boolean> = {};
    rolePresets[preset].forEach(key => { next[key] = true; });
    setPermissions(next);
  };

  const setGroupPermissions = (group: PermissionGroup, enabled: boolean) => {
    setPermissions(prev => {
      const next = { ...prev };
      group.items.forEach(item => { next[item.key] = enabled; });
      return next;
    });
  };

  const deleteSelectedRole = async () => {
    if (!selectedRole || selectedRole.name === 'superadmin') return;
    if (!confirm(`Удалить роль ${selectedRole.name}? Пользователи с этой ролью останутся без роли.`)) return;
    await api.deleteRole(selectedRole.id);
    setSelectedRoleId(null);
    setPermissions({});
    setRoleName('');
    await load();
  };

  if (loading) return <div className="grid h-64 place-items-center text-sm text-[var(--color-text-secondary)]">Загрузка пользователей...</div>;

  const selectedRole = roles.find(role => role.id === selectedRoleId);
  const enabledCount = Object.values(permissions).filter(Boolean).length;
  const filteredGroups = permissionGroups
    .map(group => ({
      ...group,
      items: group.items.filter(item => {
        const query = permissionSearch.trim().toLocaleLowerCase('ru-RU');
        return !query || `${item.label} ${item.hint} ${item.key}`.toLocaleLowerCase('ru-RU').includes(query);
      }),
    }))
    .filter(group => group.items.length);

  return (
    <div className="mx-auto max-w-[1500px] space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-black">Пользователи и права</h2>
          <p className="text-sm text-[var(--color-text-secondary)]">Superadmin защищён, его права не редактируются и не удаляются. Остальные роли можно настраивать по разделам.</p>
        </div>
        <button onClick={() => setShowModal(true)} className="tf-button tf-button-primary"><Plus size={16} />Создать</button>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(520px,.9fr)_minmax(0,1.35fr)]">
      <section className="tf-panel-flat overflow-hidden">
        <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-4 py-3">
          <UsersRound size={17} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-black">Команда</h3>
        </div>
        <div className="overflow-x-auto">
        <div className="grid min-w-[680px] grid-cols-[1fr_220px_90px] gap-3 border-b border-[var(--color-border)] px-4 py-3 text-xs font-semibold text-[var(--color-text-secondary)]">
          <span>Пользователь</span>
          <span>Роль</span>
          <span />
        </div>
        {users.map(user => {
          const protectedUser = isProtectedSuperadmin(user, users);
          const hasSuperadmin = isSuperadmin(user);
          return (
            <div key={user.id} className="grid min-w-[680px] grid-cols-[1fr_220px_90px] items-center gap-3 border-b border-[var(--color-border)]/60 px-4 py-3 last:border-b-0 hover:bg-[var(--color-surface-2)]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate text-sm font-semibold">{user.username}</span>
                  {currentUser?.id === user.id && <span className="tf-chip text-[var(--color-accent)]">это вы</span>}
                  {hasSuperadmin && <span className="tf-chip text-[var(--color-warning)]"><ShieldCheck size={13} />{protectedUser ? 'защищён' : 'superadmin'}</span>}
                </div>
              </div>
              {protectedUser ? (
                <div className="text-sm font-semibold text-[var(--color-text-secondary)]">superadmin</div>
              ) : (
                <select value={user.roles?.[0]?.id || ''} onChange={event => handleSetRole(user.id, Number(event.target.value))} className="tf-input h-9 text-sm">
                  <option value="">Без роли</option>
                  {roles.filter(role => role.name !== 'superadmin').map(role => <option key={role.id} value={role.id}>{role.name}</option>)}
                </select>
              )}
              <div className="flex justify-end">
                {currentUser?.id !== user.id && !protectedUser && (
                  <button onClick={() => handleDelete(user)} className="tf-button text-[var(--color-danger)]" title="Удалить"><Trash2 size={15} /></button>
                )}
              </div>
            </div>
          );
        })}
        </div>
      </section>

      <section className="tf-panel-flat p-4">
        <div className="mb-4 grid gap-3 lg:grid-cols-[220px_minmax(180px,1fr)_auto_auto]">
          <select className="tf-input" value={selectedRoleId || ''} onChange={event => selectRole(Number(event.target.value))}>
            <option value="">Выберите роль</option>
            {roles.filter(role => role.name !== 'superadmin').map(role => <option key={role.id} value={role.id}>{role.name}</option>)}
          </select>
          <input className="tf-input" value={roleName} onChange={event => setRoleName(event.target.value)} placeholder="Название роли" disabled={!selectedRole || selectedRole.name === 'superadmin'} />
          <button onClick={saveRolePermissions} disabled={!selectedRole || selectedRole.name === 'superadmin'} className="tf-button tf-button-primary"><Save size={15} />Сохранить</button>
          <button onClick={deleteSelectedRole} disabled={!selectedRole || selectedRole.name === 'superadmin'} className="tf-button text-[var(--color-danger)]"><Trash2 size={15} />Удалить</button>
        </div>
        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(220px,1fr)_auto]">
          <div className="flex flex-wrap gap-2">
            <input className="tf-input max-w-xs" value={newRoleName} onChange={event => setNewRoleName(event.target.value)} placeholder="Название новой роли" />
            <button type="button" onClick={createRole} className="tf-button"><Plus size={15} />Добавить роль</button>
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <button type="button" className="tf-button" onClick={() => applyPreset('executor')}>Исполнитель</button>
            <button type="button" className="tf-button" onClick={() => applyPreset('manager')}>Менеджер</button>
            <button type="button" className="tf-button" onClick={() => applyPreset('admin')}>Админ</button>
          </div>
        </div>
        <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
          <label className="relative">
            <Search size={15} className="pointer-events-none absolute left-3 top-[12px] text-[var(--color-muted)]" />
            <input className="tf-input tf-input-icon" value={permissionSearch} onChange={event => setPermissionSearch(event.target.value)} placeholder="Найти право" />
          </label>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text-secondary)]">
            Включено прав: <span className="font-black text-[var(--color-text)]">{enabledCount}</span>
          </div>
        </div>
        {selectedRole?.name === 'superadmin' ? (
          <div className="text-sm text-[var(--color-text-secondary)]">Права superadmin не редактируются.</div>
        ) : (
          <div className="grid gap-4 2xl:grid-cols-2">
            {filteredGroups.map(group => {
              const Icon = group.icon;
              const groupEnabled = group.items.filter(item => permissions[item.key]).length;
              return (
              <div key={group.title} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-black"><Icon size={16} className="text-[var(--color-accent)]" />{group.title}</div>
                    <div className="mt-1 text-xs leading-5 text-[var(--color-text-secondary)]">{group.description}</div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button type="button" className="tf-button h-8 px-2 text-xs" onClick={() => setGroupPermissions(group, true)}>Все</button>
                    <button type="button" className="tf-button h-8 px-2 text-xs" onClick={() => setGroupPermissions(group, false)}>Нет</button>
                  </div>
                </div>
                <div className="space-y-2">
                  {group.items.map(item => (
                    <label key={item.key} className="flex items-start gap-3 rounded-lg border border-[var(--color-border)]/70 bg-[var(--color-surface)] px-3 py-2 text-sm">
                      <input className="mt-1 accent-[var(--color-accent)]" type="checkbox" checked={Boolean(permissions[item.key])} onChange={event => setPermissions(prev => ({ ...prev, [item.key]: event.target.checked }))} />
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2 font-semibold">
                          {item.label}
                          {item.level === 'sensitive' && <span className="tf-chip text-[var(--color-warning)]"><Lock size={12} />важное</span>}
                          {item.level === 'advanced' && <span className="tf-chip text-[var(--color-accent)]">расширенное</span>}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-[var(--color-text-secondary)]">{item.hint}</span>
                      </span>
                    </label>
                  ))}
                </div>
                <div className="mt-3 text-xs text-[var(--color-muted)]">Включено в группе: {groupEnabled} из {group.items.length}</div>
              </div>
            );})}
          </div>
        )}
      </section>
      </div>

      {showModal && <CreateUserModal onClose={() => setShowModal(false)} onCreate={handleCreate} />}
    </div>
  );
}

function isSuperadmin(user: User) {
  return user.roles?.some(role => role.name === 'superadmin');
}

function isProtectedSuperadmin(user: User, users: User[]) {
  if (!isSuperadmin(user)) return false;
  return users.filter(isSuperadmin).length <= 1;
}

function CreateUserModal({ onClose, onCreate }: { onClose: () => void; onCreate: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    await onCreate(username, password);
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" onClick={onClose}>
      <form onSubmit={submit} className="tf-panel w-full max-w-sm p-5" onClick={event => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-black">Новый пользователь</h2>
          <button type="button" onClick={onClose} className="tf-button"><X size={16} /></button>
        </div>
        <div className="space-y-3">
          <label><span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Логин</span><input className="tf-input" value={username} onChange={event => setUsername(event.target.value)} required minLength={2} /></label>
          <label><span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Пароль</span><input className="tf-input" type="password" value={password} onChange={event => setPassword(event.target.value)} required minLength={4} /></label>
          <button disabled={saving} className="tf-button tf-button-primary w-full">{saving ? 'Создание...' : 'Создать пользователя'}</button>
        </div>
      </form>
    </div>
  );
}
