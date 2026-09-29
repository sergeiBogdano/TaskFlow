import { useEffect, useState, type FormEvent } from 'react';
import { Building2, KeyRound, LayoutDashboard, ListChecks, Lock, Plus, Save, Search, Settings2, ShieldCheck, Trash2, UsersRound, X } from 'lucide-react';
import { api } from '../api/client';
import type { PermissionCatalog, PermissionGroup, Role, User } from '../api/client';
import { SearchSelect } from '../components/SearchSelect';
import { useAuth } from '../hooks/useAuth';
import { roleMeta } from '../lib/taskflow';

const groupIcons: Record<string, typeof LayoutDashboard> = {
  navigation: LayoutDashboard,
  tasks: ListChecks,
  clients: Building2,
  system: Settings2,
};

const roleLabel = (role: Role) => roleMeta[role.name]?.label || role.name;

export function Users() {
  const { user: currentUser } = useAuth();
  const isSuperadminActor = Boolean(currentUser?.permissions?.all);
  const canGrant = (key: string) => isSuperadminActor || Boolean(currentUser?.permissions?.[key]);
  const canGrantRole = (role: Role) =>
    isSuperadminActor || Object.entries(role.permissions || {}).every(([key, value]) => !value || canGrant(key));
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [pwdUserId, setPwdUserId] = useState<number | null>(null);
  const [pwdValue, setPwdValue] = useState('');
  const [pwdError, setPwdError] = useState('');
  const [newRoleName, setNewRoleName] = useState('');
  const [roleName, setRoleName] = useState('');
  const [permissionSearch, setPermissionSearch] = useState('');
  const [permissionTab, setPermissionTab] = useState<'app' | 'work'>('work');

  const load = async () => {
    const [userList, roleList, permissionCatalog] = await Promise.all([
      api.getUsers(),
      api.getRoles(),
      api.getPermissionCatalog(),
    ]);
    setUsers(userList);
    setRoles(roleList);
    setCatalog(permissionCatalog);
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

  const savePassword = async (userId: number) => {
    if (pwdValue.length < 4) {
      setPwdError('Пароль минимум 4 символа.');
      return;
    }
    setPwdError('');
    try {
      await api.setUserPassword(userId, pwdValue);
      setPwdUserId(null);
      setPwdValue('');
    } catch (err) {
      setPwdError(err instanceof Error ? err.message : 'Не удалось сменить пароль.');
    }
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

  const handleCreate = async (username: string, password: string, workspaceId?: string, wsRole?: string) => {
    await api.createUser(
      username,
      password,
      workspaceId ? { workspace_id: Number(workspaceId), role: wsRole || 'member' } : undefined,
    );
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

  const applyPreset = (preset: string) => {
    const next: Record<string, boolean> = {};
    (catalog?.presets[preset] || []).forEach(key => {
      if (canGrant(key)) next[key] = true;
    });
    setPermissions(next);
  };

  const setGroupPermissions = (group: PermissionGroup, enabled: boolean) => {
    setPermissions(prev => {
      const next = { ...prev };
      group.items.forEach(item => {
        if (enabled && !canGrant(item.key)) return;
        next[item.key] = enabled;
      });
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
  const filteredGroups = (catalog?.groups || [])
    .filter(group => group.scope === permissionTab)
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
          <UsersRound size={19} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-black">Команда</h3>
        </div>
        <div>
        <div className="grid grid-cols-[minmax(0,1fr)_170px_52px] gap-3 border-b border-[var(--color-border)] px-4 py-3 text-xs font-semibold text-[var(--color-text-secondary)]">
          <span>Пользователь</span>
          <span>Роль</span>
          <span />
        </div>
        {users.map(user => {
          const protectedUser = isProtectedSuperadmin(user, users);
          const hasSuperadmin = isSuperadmin(user);
          return (
            <div key={user.id} className="grid grid-cols-[minmax(0,1fr)_170px_96px] items-center gap-3 border-b border-[var(--color-border)]/60 px-4 py-3 last:border-b-0 hover:bg-[var(--color-surface-2)]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate text-sm font-semibold">{user.username}</span>
                  {currentUser?.id === user.id && <span className="tf-chip text-[var(--color-accent)]">это вы</span>}
                  {hasSuperadmin && <span className="tf-chip text-[var(--color-warning)]"><ShieldCheck size={13} />{protectedUser ? 'защищён' : 'superadmin'}</span>}
                </div>
              </div>
              {hasSuperadmin ? (
                <div className="text-sm font-semibold text-[var(--color-text-secondary)]">superadmin</div>
              ) : (
                <SearchSelect
                  value={user.roles?.[0]?.id ? String(user.roles[0].id) : ''}
                  options={roles.filter(role => role.name !== 'superadmin' && canGrantRole(role)).map(role => ({ value: String(role.id), label: roleLabel(role) }))}
                  onChange={value => handleSetRole(user.id, Number(value))}
                  emptyLabel="Без роли"
                  placeholder="Роль"
                  searchPlaceholder="Найти роль..."
                />
              )}
              <div className="flex justify-end gap-1.5">
                <button onClick={() => { setPwdUserId(pwdUserId === user.id ? null : user.id); setPwdValue(''); setPwdError(''); }} className="tf-button h-9 w-9 px-0" title="Сменить пароль"><KeyRound size={15} /></button>
                {isSuperadminActor && currentUser?.id !== user.id && !protectedUser && (
                  <button onClick={() => handleDelete(user)} className="tf-button h-9 w-9 px-0 text-[var(--color-danger)]" title="Удалить"><Trash2 size={15} /></button>
                )}
              </div>
              {pwdUserId === user.id && (
                <div className="col-span-3 mt-1 flex gap-2">
                  <input
                    type="password"
                    className="tf-input h-9 text-sm"
                    value={pwdValue}
                    onChange={event => setPwdValue(event.target.value)}
                    placeholder="Новый пароль от 4 символов"
                  />
                  <button type="button" onClick={() => savePassword(user.id)} className="tf-button h-9 shrink-0 text-xs">OK</button>
                </div>
              )}
              {pwdUserId === user.id && pwdError && (
                <div className="col-span-3 text-xs font-semibold text-[var(--color-danger)]">{pwdError}</div>
              )}
            </div>
          );
        })}
        </div>
      </section>

      <section className="tf-panel-flat p-4">
        <div className="mb-4 grid gap-3 lg:grid-cols-[220px_minmax(180px,1fr)_auto_auto]">
          <SearchSelect
            value={selectedRoleId ? String(selectedRoleId) : ''}
            options={roles.map(role => ({ value: String(role.id), label: roleLabel(role) }))}
            onChange={value => selectRole(Number(value))}
            placeholder="Выберите роль"
            searchPlaceholder="Найти роль..."
          />
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
        <div className="mb-4 flex flex-wrap gap-2">
          <button type="button" className={`tf-button ${permissionTab === 'app' ? 'tf-button-primary' : ''}`} onClick={() => setPermissionTab('app')}>Приложение</button>
          <button type="button" className={`tf-button ${permissionTab === 'work' ? 'tf-button-primary' : ''}`} onClick={() => setPermissionTab('work')}>Работа</button>
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
              const Icon = groupIcons[group.id] || LayoutDashboard;
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
                  {group.items.map(item => {
                    const overCeiling = !canGrant(item.key);
                    return (
                    <label key={item.key} className={`flex items-start gap-3 rounded-lg border border-[var(--color-border)]/70 bg-[var(--color-surface)] px-3 py-2 text-sm ${overCeiling ? 'opacity-60' : ''}`}>
                      <input className="mt-1 accent-[var(--color-accent)]" type="checkbox" disabled={overCeiling} checked={Boolean(permissions[item.key])} onChange={event => setPermissions(prev => ({ ...prev, [item.key]: event.target.checked }))} />
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2 font-semibold">
                          {item.label}
                          {item.level === 'sensitive' && <span className="tf-chip text-[var(--color-warning)]"><Lock size={12} />важное</span>}
                          {item.level === 'advanced' && <span className="tf-chip text-[var(--color-accent)]">расширенное</span>}
                          {overCeiling && <span className="tf-chip text-[var(--color-danger)]">нет у вас прав</span>}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-[var(--color-text-secondary)]">{item.hint}</span>
                      </span>
                    </label>
                    );
                  })}
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

function CreateUserModal({ onClose, onCreate }: { onClose: () => void; onCreate: (username: string, password: string, workspaceId?: string, wsRole?: string) => Promise<void> }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [workspaces, setWorkspaces] = useState<{ id: number; name: string }[]>([]);
  const [workspaceId, setWorkspaceId] = useState('');
  const [wsRole, setWsRole] = useState('member');
  const [formError, setFormError] = useState('');

  useEffect(() => {
    api.getWorkspaces().then(setWorkspaces).catch(() => {});
  }, []);

  const requestClose = () => {
    const dirty = username.trim() !== '' || password !== '';
    if (!dirty || confirm('Есть несохранённые данные. Закрыть без сохранения?')) onClose();
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError('');
    try {
      await onCreate(username, password, workspaceId || undefined, wsRole);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Не удалось создать.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="anim-modal fixed inset-0 z-50 grid place-items-center bg-black/55 p-4" onClick={requestClose}>
      <form onSubmit={submit} className="tf-panel w-full max-w-sm p-5" onClick={event => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-black">Новый пользователь</h2>
          <button type="button" onClick={requestClose} className="tf-button"><X size={16} /></button>
        </div>
        <div className="space-y-3">
          <label><span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Логин</span><input className="tf-input" value={username} onChange={event => setUsername(event.target.value)} required minLength={2} /></label>
          <label><span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Пароль</span><input className="tf-input" type="password" value={password} onChange={event => setPassword(event.target.value)} required minLength={4} /></label>
          <label>
            <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Сразу в окружение (необязательно)</span>
            <SearchSelect
              value={workspaceId}
              options={workspaces.map(w => ({ value: String(w.id), label: w.name }))}
              onChange={setWorkspaceId}
              placeholder="Без окружения"
              searchPlaceholder="Найти окружение..."
            />
          </label>
          {workspaceId && (
            <label>
              <span className="mb-1 block text-xs font-semibold text-[var(--color-text-secondary)]">Роль в окружении</span>
              <select className="tf-input" value={wsRole} onChange={event => setWsRole(event.target.value)}>
                <option value="member">Участник</option>
                <option value="admin">Админ</option>
              </select>
            </label>
          )}
          {formError && <div className="text-sm font-semibold text-[var(--color-danger)]">{formError}</div>}
          <button disabled={saving} className="tf-button tf-button-primary w-full">{saving ? 'Создание...' : 'Создать пользователя'}</button>
        </div>
      </form>
    </div>
  );
}
