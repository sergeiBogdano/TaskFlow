import { useCallback, useEffect, useRef, useState } from 'react';
import { Power } from 'lucide-react';
import { api, type PermissionGroup } from '../api/client';

type FeaturesPanelProps = {
  scope: 'global' | 'workspace' | 'group' | 'user';
  targetId?: number;
  title?: string;
  description?: string;
  workOnly?: boolean;
  appOnly?: boolean;
};

/**
 * Кран доступности (Ф6): тумблеры функций по каталогу прав.
 * scope=global — «Настройки»; scope=workspace — настройки окружения.
 * Выключенная функция скрыта в меню и закрыта на бэке (403) для всех.
 */
export function FeaturesPanel({ scope, targetId, title, description, workOnly = false, appOnly = false }: FeaturesPanelProps) {
  const [groups, setGroups] = useState<PermissionGroup[]>([]);
  const [overrides, setOverrides] = useState<Record<string, { id: number; enabled: boolean }>>({});
  const [effective, setEffective] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState('');
  const loadRevision = useRef(0);
  const contextKey = `${scope}:${targetId ?? ''}:${workOnly}:${appOnly}`;
  const currentContext = useRef(contextKey);
  currentContext.current = contextKey;
  const [loadedContext, setLoadedContext] = useState('');

  const load = useCallback(async () => {
    if (currentContext.current !== contextKey) return;
    const revision = ++loadRevision.current;
    try {
      const data = await api.getFeatures(scope, targetId);
      if (revision !== loadRevision.current) return;
      setGroups((data.catalog || []).filter(group => appOnly ? group.scope === 'app' : (scope !== 'workspace' && !workOnly) || group.scope === 'work'));
      setEffective(data.scope_effective || {});
      const map: Record<string, { id: number; enabled: boolean }> = {};
      data.overrides
        .filter(row => row.scope === scope && (scope === 'global' ? row.target_id == null : row.target_id === targetId))
        .forEach(row => { map[row.key] = { id: row.id, enabled: row.enabled }; });
      setOverrides(map);
      setLoadedContext(contextKey);
    } catch {
      if (revision !== loadRevision.current) return;
      setMsg('Не удалось загрузить настройки функций. Обновите страницу.');
      setGroups([]);
    }
  }, [scope, targetId, workOnly, appOnly, contextKey]);

  useEffect(() => { load(); return () => { loadRevision.current++; }; }, [load]);

  const toggle = async (key: string, enabled: boolean | null) => {
    setBusy(key);
    setMsg('');
    const label = groups.flatMap(group => group.items).find(item => item.key === key)?.label || key;
    try {
      await api.setFeature({ scope, target_id: scope === 'global' ? null : targetId, key, enabled });
      await load();
      window.dispatchEvent(new Event('taskflow:access-updated'));
      setMsg(enabled === null ? 'Отдельная настройка снята: применяется наследование' : enabled ? `Для «${label}» задано разрешение функции. Также нужно право в профиле` : `Для «${label}» задан запрет на этом уровне. Проверьте итоговый доступ пользователя`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Не удалось изменить функцию');
    } finally {
      setBusy(null);
    }
  };

  if (!groups.length) return msg ? <p role="alert" className="tf-alert-error">{msg}</p> : null;

  return (
    <section className="tf-panel-flat p-5">
      <h3 className="mb-1 flex items-center gap-2 text-sm font-bold"><Power size={16} />{title || 'Доступность функций'}</h3>
      <p className="mb-3 text-sm text-[var(--color-text-secondary)]">
        {description || 'Эти настройки управляют доступностью функций, а права назначаются отдельно. Глобальный запрет закрывает функцию для обычных пользователей. Суперадмин сохраняет доступ к управлению. Выключение функции сохраняет данные и назначения профилей.'}
      </p>
      <div className="space-y-3">
        {groups.map(group => (
          <div key={group.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
            <div className="mb-2 text-xs font-black uppercase tracking-wide text-[var(--color-text-secondary)]">
              {group.title}
            </div>
            <div className="space-y-1.5">
              {group.items.map(item => {
                const off = effective[item.key] !== true;
                const overridden = overrides[item.key];
                return (
                  <label key={item.key} className={`flex flex-col items-start justify-between gap-3 rounded-lg sm:flex-row border border-[var(--color-border)]/70 bg-[var(--color-surface)] px-3 py-2 text-sm ${item.key === 'settings' ? 'opacity-70' : ''}`}>
                    <span className="min-w-0">
                      <span className="font-semibold">{item.label}</span>
                      <span className="mt-0.5 block text-xs text-[var(--color-text-secondary)]">{item.hint}</span>
                      <span className={`mt-0.5 block text-xs ${off ? 'text-[var(--color-muted)]' : 'text-[var(--color-success)]'}`}>{off ? 'Итог: функция закрыта' : 'Итог: функция разрешена, требуется право'}</span>
                      {overridden && (
                        <span className="mt-0.5 block text-[11px] font-semibold text-[var(--color-accent)]">
                          переопределено: {overridden.enabled ? 'включено' : 'выключено'}
                        </span>
                      )}
                    </span>
                    {scope !== 'global' ? <select className="tf-input mt-1 w-full shrink-0 sm:w-44" aria-label={`Доступность: ${item.label}`} disabled={busy !== null || loadedContext !== contextKey || item.key === 'settings'} value={overridden ? String(overridden.enabled) : ''} onChange={event => void toggle(item.key, event.target.value === '' ? null : event.target.value === 'true')}><option value="">Наследовать</option><option value="true">Разрешить функцию</option><option value="false">Запретить функцию</option></select> : <input
                      className="mt-1 accent-[var(--color-accent)]"
                      type="checkbox"
                      disabled={busy !== null || loadedContext !== contextKey || item.key === 'settings'}
                      checked={!off}
                      onChange={event => toggle(item.key, event.target.checked)}
                      title={item.key === 'settings' ? 'Эту функцию нельзя выключить — на ней держится панель управления' : undefined}
                    />}
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
