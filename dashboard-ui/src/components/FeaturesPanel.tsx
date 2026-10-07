import { useCallback, useEffect, useState } from 'react';
import { Power } from 'lucide-react';
import { api, type PermissionGroup } from '../api/client';

type FeaturesPanelProps = {
  scope: 'global' | 'workspace';
  targetId?: number;
  title?: string;
  description?: string;
};

/**
 * Кран доступности (Ф6): тумблеры функций по каталогу прав.
 * scope=global — «Настройки»; scope=workspace — настройки окружения.
 * Выключенная функция скрыта в меню и закрыта на бэке (403) для всех.
 */
export function FeaturesPanel({ scope, targetId, title, description }: FeaturesPanelProps) {
  const [groups, setGroups] = useState<PermissionGroup[]>([]);
  const [overrides, setOverrides] = useState<Record<string, { id: number; enabled: boolean }>>({});
  const [effective, setEffective] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    try {
      const data = await api.getFeatures();
      setGroups(data.catalog || []);
      setEffective(data.effective || {});
      const map: Record<string, { id: number; enabled: boolean }> = {};
      data.overrides
        .filter(row => row.scope === scope && (scope === 'global' ? row.target_id == null : row.target_id === targetId))
        .forEach(row => { map[row.key] = { id: row.id, enabled: row.enabled }; });
      setOverrides(map);
    } catch {
      // не суперадмин — панель просто не показывается
      setGroups([]);
    }
  }, [scope, targetId]);

  useEffect(() => { load(); }, [load]);

  const toggle = async (key: string, enabled: boolean) => {
    setBusy(key);
    setMsg('');
    try {
      await api.setFeature({ scope, target_id: scope === 'workspace' ? targetId : null, key, enabled });
      await load();
      setMsg(enabled ? `Функция «${key}» включена` : `Функция «${key}» выключена — она скрыта и закрыта для пользователей`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Не удалось изменить функцию');
    } finally {
      setBusy(null);
    }
  };

  if (!groups.length) return null;

  return (
    <section className="tf-panel-flat p-5">
      <h3 className="mb-1 flex items-center gap-2 text-sm font-bold"><Power size={16} />{title || 'Функции контура'}</h3>
      <p className="mb-3 text-sm text-[var(--color-text-secondary)]">
        {description || 'Кран доступности: выключенная функция исчезает из меню и возвращает 403 на бэке — у обычных пользователей. Суперадмин сохраняет доступ к управлению. Выдачи прав в ролях при этом не трогаются.'}
      </p>
      <div className="space-y-3">
        {groups.map(group => (
          <div key={group.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
            <div className="mb-2 text-xs font-black uppercase tracking-wide text-[var(--color-text-secondary)]">
              {group.title}
            </div>
            <div className="space-y-1.5">
              {group.items.map(item => {
                const off = overrides[item.key]?.enabled === false || (!overrides[item.key] && effective[item.key] === false);
                const overridden = overrides[item.key];
                return (
                  <label key={item.key} className={`flex items-start justify-between gap-3 rounded-lg border border-[var(--color-border)]/70 bg-[var(--color-surface)] px-3 py-2 text-sm ${item.key === 'settings' ? 'opacity-70' : ''}`}>
                    <span className="min-w-0">
                      <span className="font-semibold">{item.label}</span>
                      <span className="mt-0.5 block text-xs text-[var(--color-text-secondary)]">{item.hint}</span>
                      {overridden && (
                        <span className="mt-0.5 block text-[11px] font-semibold text-[var(--color-accent)]">
                          переопределено: {overridden.enabled ? 'включено' : 'выключено'}
                        </span>
                      )}
                    </span>
                    <input
                      className="mt-1 accent-[var(--color-accent)]"
                      type="checkbox"
                      disabled={busy === item.key || item.key === 'settings'}
                      checked={!off}
                      onChange={event => toggle(item.key, event.target.checked)}
                      title={item.key === 'settings' ? 'Эту функцию нельзя выключить — на ней держится панель управления' : undefined}
                    />
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {msg && <p className="mt-3 text-sm text-[var(--color-text-secondary)]">{msg}</p>}
    </section>
  );
}
