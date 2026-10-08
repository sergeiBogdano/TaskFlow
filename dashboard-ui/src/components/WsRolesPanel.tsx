import { FieldAccessEditor } from './FieldAccessEditor';
import type { FieldAccess } from '../lib/fieldAccess';
import { useCallback, useEffect, useState } from 'react';
import { Pencil, Plus, ShieldCheck, Trash2, RotateCcw, X } from 'lucide-react';
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
 * Конструктор кастомных ролей окружения.
 * Только scope=work-ключи; чекбоксы, отключённые краном доступности, скрыты;
 * чекбоксы вне потолка выдающего — disabled.
 * Кастомная роль — ТОЧНЫЙ итоговый набор прав участника: что отмечено,
 * то и действует, база ранга не добавляется. Ранг (owner/admin/member)
 * при этом сохраняется и отвечает только за управление окружением.
 */
export function WsRolesPanel({ workspaceId, canManage }: WsRolesPanelProps) {
  const { user } = useAuth();
  const isSuper = Boolean(user?.permissions?.all);
  const canGrant = (key: string) => isSuper || Boolean(user?.permissions?.[key]);

  const [formOpen, setFormOpen] = useState(false);
  const [roles, setRoles] = useState<WorkspaceRole[]>([]);
  const [deletedRoles, setDeletedRoles] = useState<WorkspaceRole[]>([]);
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [fieldAccess, setFieldAccess] = useState<FieldAccess>({});
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [data, cat, archived] = await Promise.all([
        api.getWsRoles(workspaceId),
        api.getPermissionCatalog().catch(() => null),
        api.getWsRoles(workspaceId, true),
      ]);
      setRoles(data.roles);
      setDeletedRoles(archived.roles);
      setFeatures(data.features || {});
      setCatalog(cat);
    } catch (err) {
      setRoles([]);
      setDeletedRoles([]);
      setMsg(err instanceof Error ? err.message : 'Не удалось загрузить профили');
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const groups: PermissionGroup[] = (catalog?.groups || []).filter(group => group.scope === 'work');

  const startEdit = (role: WorkspaceRole) => {
    setFormOpen(true);
    setEditingId(role.id);
    setName(role.name);
    setPermissions({ ...role.permissions });
    setFieldAccess({ ...role.field_access });
    setMsg('');
  };

  const cancelEdit = () => {
    setFormOpen(false);
    setEditingId(null);
    setName('');
    setPermissions({});
    setFieldAccess({});
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
        await api.createWsRole(workspaceId, { name: name.trim(), permissions, field_access: fieldAccess });
        setMsg(`Роль «${name.trim()}» создана.`);
      } else {
        await api.updateWsRole(workspaceId, editingId, { name: name.trim(), permissions, field_access: fieldAccess });
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
    if (!confirm(`Удалить роль «${role.name}»? Если она назначена участникам, сначала смените их профили доступа.`)) return;
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

  const applyBasePreset = (kind: 'member' | 'admin') => {
    setPermissions(prev => {
      const next = { ...prev };
      groups.forEach(group => group.items.forEach(item => {
        if (features[item.key] === false) return;
        if (!canGrant(item.key)) return;
        next[item.key] = kind === 'admin' ? true : item.level === 'basic';
      }));
      return next;
    });
    setMsg(kind === 'admin'
      ? 'Предзаполнено как у админа (полный набор). Снимите лишнее.'
      : 'Предзаполнено как у участника (базовые). Отметьте нужное.');
  };

  const visibleGroups = groups.map(group => ({
    ...group,
    items: group.items,
  }));

  const permissionCount = (role: WorkspaceRole) =>
    Object.values(role.permissions || {}).filter(Boolean).length;

  return (
    <section className="tf-panel-flat p-5">
      <div className="mb-1 flex items-center gap-2 text-sm font-bold">
        <ShieldCheck size={16} />Профили доступа окружения
        <span className="tf-chip ml-auto">Профилей: {roles.length}</span>
      </div>
      <p className="mb-3 text-xs text-[var(--color-text-secondary)]">
        Профиль — набор разрешённых рабочих и административных действий и доступа к полям.
        Уровень участника (владелец/администратор/участник) ограничивает, кого можно изменять.
        Личные исключения уточняют профиль. Выключенная функция или модуль блокируют действие независимо от профиля.
      </p>

      {canManage && !formOpen && <button type="button" className="tf-button mb-4" onClick={() => setFormOpen(true)}><Plus size={15} />Новый профиль доступа</button>}
      {canManage && formOpen && (
        <div className="mb-4 space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-black uppercase tracking-wide text-[var(--color-text-secondary)]">
              {editingId == null ? 'Новый профиль' : 'Редактирование профиля'}
            </span>
            <button type="button" onClick={() => applyBasePreset('member')} className="tf-button h-8 px-2 text-xs" title="Отметить базовый набор участника">
              Как участник
            </button>
            <button type="button" onClick={() => applyBasePreset('admin')} className="tf-button h-8 px-2 text-xs" title="Отметить полный набор">
              Как админ
            </button>
            {formOpen && (
              <button type="button" onClick={cancelEdit} className="tf-button h-8 px-2 text-xs">
                <X size={14} />Отмена
              </button>
            )}
          </div>
          <input
            className="tf-input"
            value={name}
            onChange={event => setName(event.target.value)}
            placeholder="Название профиля (например, «Участник проекта»)"
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
                            <span className="mt-0.5 block text-xs text-[var(--color-text-secondary)]">{item.hint}{features[item.key] === false ? ' · Функция или модуль отключены' : overCeiling ? ' · Вы не можете выдать это право' : ''}</span>
                          </span>
                          <input
                            className="mt-1 accent-[var(--color-accent)]"
                            type="checkbox"
                            disabled={overCeiling || features[item.key] === false}
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
          <FieldAccessEditor value={fieldAccess} onChange={setFieldAccess} disabled={busy} />
          <button type="button" className="tf-button tf-button-primary" onClick={save} disabled={busy}>
            {busy ? 'Сохранение...' : editingId == null ? 'Создать профиль' : 'Сохранить'}
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
                    disabled={busy}
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
          <div className="text-sm text-[var(--color-text-secondary)]">Профилей пока нет. Создайте профиль, затем назначьте его участнику выше.</div>
        )}
      </div>
      {canManage && <details className="mt-4 rounded-xl border border-[var(--color-border)] p-3"><summary className="cursor-pointer text-sm font-semibold">Удалённые профили · {deletedRoles.length}</summary><p className="my-3 text-xs text-[var(--color-muted)]">Назначенный участникам профиль нельзя удалить. Сначала явно выберите для них другие профили. Восстановленный профиль нужно назначать вручную.</p>{deletedRoles.map(item => <div key={item.id} className="flex flex-wrap items-center gap-2 border-t border-[var(--color-border)] py-2"><span className="flex-1 text-sm">{item.name}</span><button disabled={busy} className="tf-button" onClick={async () => { setBusy(true); setMsg(''); try { await api.restoreWsRole(workspaceId, item.id); await load(); } catch (err) { setMsg(err instanceof Error ? err.message : 'Не удалось восстановить профиль'); } finally { setBusy(false); } }}><RotateCcw size={14} />Восстановить</button></div>)}{!deletedRoles.length && <p className="text-xs text-[var(--color-muted)]">Удалённых профилей нет.</p>}</details>}
      {msg && <p className="mt-3 text-sm text-[var(--color-text-secondary)]">{msg}</p>}
    </section>
  );
}
