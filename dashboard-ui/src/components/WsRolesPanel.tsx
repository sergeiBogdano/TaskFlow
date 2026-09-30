import { useCallback, useEffect, useState } from 'react';
import { Pencil, Plus, ShieldCheck, Trash2, X } from 'lucide-react';
import {
  api,
  type PermissionCatalog,
  type PermissionGroup,
  type WorkspaceRole,
} from '../api/client';
import { useAuth } from '../hooks/useAuth';

type WsRolesPanelProps = {
  workspaceId: number;
  canManage: boolean;
};

/**
 * Ф7: конструктор кастомных ролей окружения.
 * Только scope=work-ключи; чекбоксы, отключённые краном доступности, скрыты;
 * чекбоксы вне потолка выдающего — disabled.
 */
export function WsRolesPanel({ workspaceId, canManage }: WsRolesPanelProps) {
  const { user } = useAuth();
  const isSuper = Boolean(user?.permissions?.all);
  const canGrant = (key: string) => isSuper || Boolean(user?.permissions?.[key]);

  const [roles, setRoles] = useState<WorkspaceRole[]>([]);
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [data, cat] = await Promise.all([
        api.getWsRoles(workspaceId),
        api.getPermissionCatalog().catch(() => null),
      ]);
      setRoles(data.roles);
      setFeatures(data.features || {});
      setCatalog(cat);
    } catch {
      setRoles([]);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const groups: PermissionGroup[] = (catalog?.groups || []).filter(group => group.scope === 'work');

  const startEdit = (role: WorkspaceRole) => {
    setEditingId(role.id);
    setName(role.name);
    setPermissions({ ...role.permissions });
    setMsg('');
  };

  const cancelEdit = () => {
    setEditingId(null);
    setName('');
    setPermissions({});
    setMsg('');
  };

  const save = async () => {
    if (!name.trim()) {
      setMsg('Укажите название роли.');
      return;
    }
    setBusy(true);
    setMsg('');
    try {
      if (editingId == null) {
        await api.createWsRole(workspaceId, { name: name.trim(), permissions });
        setMsg(`Роль «${name.trim()}» создана.`);
      } else {
        await api.updateWsRole(workspaceId, editingId, { name: name.trim(), permissions });
        setMsg(`Роль «${name.trim()}» обновлена.`);
      }
      cancelEdit();
      await load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Не удалось сохранить роль.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (role: WorkspaceRole) => {
    if (!confirm(`Удалить роль «${role.name}»? Назначения будут сняты.`)) return;
    setBusy(true);
    try {
      await api.deleteWsRole(workspaceId, role.id);
      if (editingId === role.id) cancelEdit();
      await load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Не удалось удалить роль.');
    } finally {
      setBusy(false);
    }
  };

  const toggleGroup = (group: PermissionGroup, enabled: boolean) => {
    setPermissions(prev => {
      const next = { ...prev };
      group.items.forEach(item => {
        if (features[item.key] === false) return;
        if (enabled && !canGrant(item.key)) return;
        next[item.key] = enabled;
      });
      return next;
    });
  };

  const visibleGroups = groups.map(group => ({
    ...group,
    items: group.items.filter(item => features[item.key] !== false),
  }));

  const permissionCount = (role: WorkspaceRole) =>
    Object.values(role.permissions || {}).filter(Boolean).length;

  return (
    <section className="tf-panel-flat p-5">
      <div className="mb-1 flex items-center gap-2 text-sm font-bold">
        <ShieldCheck size={16} />Роли окружения
        <span className="tf-chip ml-auto">Ролей: {roles.length}</span>
      </div>
      <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
        Кастомные роли — только права «Работы». Владелец и администратор окружения по умолчанию
        имеют полный набор, участник — базовый; кастомная роль назначается участнику дополнительно.
        Отключённые краном доступности функции в конструкторе не показываются.
      </p>

      {canManage && (
        <div className="mb-4 space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-black uppercase tracking-wide text-[var(--color-text-secondary)]">
              {editingId == null ? 'Новая роль' : 'Редактирование роли'}
            </span>
            {editingId != null && (
              <button type="button" onClick={cancelEdit} className="tf-button h-8 px-2 text-xs">
                <X size={14} />Отмена
              </button>
            )}
          </div>
          <input
            className="tf-input"
            value={name}
            onChange={event => setName(event.target.value)}
            placeholder="Название роли (например, «Трафик-менеджер»)"
            maxLength={100}
          />
          {visibleGroups.length > 0 ? (
            <div className="space-y-3">
              {visibleGroups.map(group => (
                <div key={group.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-xs font-black uppercase tracking-wide text-[var(--color-text-secondary)]">
                      {group.title}
                    </span>
                    <button
                      type="button"
                      className="tf-button h-7 px-2 text-[11px]"
                      onClick={() => toggleGroup(group, true)}
                    >
                      <Plus size={12} />Все
                    </button>
                  </div>
                  <div className="space-y-1.5">
                    {group.items.map(item => {
                      const overCeiling = !canGrant(item.key);
                      return (
                        <label
                          key={item.key}
                          className={`flex items-start justify-between gap-3 rounded-lg border border-[var(--color-border)]/70 px-3 py-2 text-sm ${overCeiling ? 'opacity-60' : ''}`}
                        >
                          <span className="min-w-0">
                            <span className="font-semibold">{item.label}</span>
                            <span className="mt-0.5 block text-xs text-[var(--color-text-secondary)]">{item.hint}</span>
                          </span>
                          <input
                            className="mt-1 accent-[var(--color-accent)]"
                            type="checkbox"
                            disabled={overCeiling}
                            checked={Boolean(permissions[item.key])}
                            onChange={event =>
                              setPermissions(prev => ({ ...prev, [item.key]: event.target.checked }))
                            }
                          />
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-secondary)]">Каталог прав недоступен.</p>
          )}
          <button type="button" className="tf-button tf-button-primary" onClick={save} disabled={busy}>
            {busy ? 'Сохранение...' : editingId == null ? 'Создать роль' : 'Сохранить'}
          </button>
        </div>
      )}

      <div className="space-y-2">
        {roles.map(role => (
          <div key={role.id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm font-semibold">{role.name}</span>
              <span className="tf-chip">прав: {permissionCount(role)}</span>
              {canManage && (
                <>
                  <button
                    type="button"
                    onClick={() => startEdit(role)}
                    className="tf-button h-9 px-2 text-xs"
                    title="Редактировать"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(role)}
                    className="tf-button h-9 w-9 px-0 text-[var(--color-danger)]"
                    title="Удалить"
                    aria-label={`Удалить роль ${role.name}`}
                  >
                    <Trash2 size={15} />
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
        {roles.length === 0 && (
          <div className="text-sm text-[var(--color-text-secondary)]">Кастомных ролей нет.</div>
        )}
      </div>
      {msg && <p className="mt-3 text-sm text-[var(--color-text-secondary)]">{msg}</p>}
    </section>
  );
}
